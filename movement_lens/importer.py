"""Bounded ZIP/NPZ parsing. Imported arrays never execute pickle payloads."""
import io
import json
import math
import shutil
import stat
import time
import uuid
import zipfile
from pathlib import PurePosixPath

import numpy as np

from .features import JOINTS, VERSION, describe, interval_union
from .store import sha_file, digest

MAX_ZIP_BYTES = 1024**3
MAX_EXPANDED_BYTES = 2 * 1024**3
MAX_FILES = 30000


def archive_entries(z, limit=MAX_EXPANDED_BYTES):
    entries = z.infolist()
    if len(entries) > MAX_FILES or sum(x.file_size for x in entries) > limit:
        raise ValueError('Archive is too large to import safely')
    names = set()
    for x in entries:
        p = PurePosixPath(x.filename)
        if (p.is_absolute() or '..' in p.parts or '\\' in x.filename or ':' in x.filename
                or x.filename in names or stat.S_ISLNK(x.external_attr >> 16) or x.flag_bits & 1):
            raise ValueError('Archive contains an unsafe, encrypted or duplicate path')
        names.add(x.filename)
    return names


def read_json(z, name, max_bytes=30*1024**2):
    if name not in z.namelist() or z.getinfo(name).file_size > max_bytes:
        raise ValueError(f'Missing or oversized {name}')
    try:
        return json.loads(z.read(name), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError(f'Invalid JSON in {name}') from None


def load_arrays(payload, row):
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            archive_entries(z, limit=4*1024**2)
            for member in z.infolist():
                with z.open(member) as stream:
                    version = np.lib.format.read_magic(stream)
                    reader = { (1, 0): np.lib.format.read_array_header_1_0,
                               (2, 0): np.lib.format.read_array_header_2_0 }.get(version)
                    if reader is None:
                        raise ValueError('Unsupported NPZ array header')
                    shape, _, dtype = reader(stream, max_header_size=4096)
                    size = math.prod(shape) * dtype.itemsize
                    if dtype.hasobject or dtype.kind not in 'biuf' or size > 4*1024**2 or size > member.file_size:
                        raise ValueError('Unsafe or oversized NPZ array')
        with np.load(io.BytesIO(payload), allow_pickle=False) as f:
            required = {'times', 'keypoints', 'kp_conf', 'bbox', 'valid_mask', 'source_times',
                        'observed_keypoints', 'observed_bbox', 'source_frame_indices', 'interpolated'}
            if not required <= set(f.files):
                raise ValueError('Window lacks required source observations or validity masks; export from current Touchline')
            a = {k: f[k] for k in required}
    except (zipfile.BadZipFile, OSError, TypeError):
        raise ValueError('Invalid or unsupported window NPZ') from None
    count = len(a['source_times'])
    shapes = {'times': (50,), 'keypoints': (50, 17, 2), 'kp_conf': (50, 17), 'bbox': (50, 4),
              'valid_mask': (50, 17), 'interpolated': (50,), 'source_times': (count,),
              'source_frame_indices': (count,), 'observed_keypoints': (count, 17, 3), 'observed_bbox': (count, 4)}
    if not 5 <= count <= 1000:
        raise ValueError('Invalid original observation count')
    for key, shape in shapes.items():
        x = a[key]
        if x.shape != shape or x.dtype.kind not in 'biuf' or not np.isfinite(x).all():
            raise ValueError(f'Invalid array shape or values: {key}')
    if not np.isin(a['valid_mask'], [0, 1]).all() or not np.isin(a['interpolated'], [0, 1]).all():
        raise ValueError('Validity and interpolation masks must be boolean')
    if np.any((a['kp_conf'] < 0) | (a['kp_conf'] > 1)):
        raise ValueError('Keypoint confidence must lie between zero and one')
    observed_conf = a['observed_keypoints'][:, :, 2]
    if np.any((observed_conf < 0) | (observed_conf > 1)) or a['source_frame_indices'].dtype.kind not in 'iu':
        raise ValueError('Invalid original confidence or non-integer source frame indices')
    if np.any(np.diff(a['source_times']) <= 0) or np.any(np.diff(a['source_frame_indices']) <= 0):
        raise ValueError('Original observations must have increasing times/frame indices')
    expected = row['start'] + np.arange(50)/25
    if not np.allclose(a['times'], expected, atol=1e-5, rtol=0):
        raise ValueError('Expected 50 half-open samples at 25 Hz')
    if a['source_times'][0] < row['start'] - 1e-5 or a['source_times'][-1] >= row['end'] + 1e-5:
        raise ValueError('Source observations lie outside their window')
    return a


def import_dataset(store, upload_path, filename, progress=lambda *_: None):
    staging = store.root / 'uploads' / uuid.uuid4().hex
    staging.mkdir()
    try:
        if upload_path.stat().st_size > MAX_ZIP_BYTES:
            raise ValueError('ZIP exceeds the 1 GB local import limit')
        file_hash = sha_file(upload_path)
        identity = 'd_' + digest([file_hash, VERSION])[:24]
        try:
            store.read('datasets', identity)
            return {'dataset_id': identity, 'already_imported': True}
        except KeyError:
            pass
        with zipfile.ZipFile(upload_path) as z:
            names = archive_entries(z)
            manifest = read_json(z, 'manifest.json')
            windows = read_json(z, 'windows.json')
            tracks = read_json(z, 'tracklets.json')
            if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
                raise ValueError('Expected Touchline dataset schema version 1')
            if manifest.get('keypoint_order') != JOINTS or manifest.get('timestamp_basis') != 'original_source_seconds' or manifest.get('intervals') != '[start,end)':
                raise ValueError('Unsupported joint order, timestamp basis or interval convention')
            source = manifest.get('source', {})
            sha = source.get('sha256', '')
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('A valid source SHA-256 is required')
            for key in ('width', 'height', 'fps'):
                if not isinstance(source.get(key), (int, float)) or not math.isfinite(source[key]) or source[key] <= 0:
                    raise ValueError(f'Missing source {key}')
            if not isinstance(windows, list) or not windows or len(windows) > 10000 or manifest.get('window_count') != len(windows):
                raise ValueError('Export must contain 1–10,000 windows with a matching count')
            if not isinstance(tracks, list) or len(tracks) != manifest.get('tracklet_count'):
                raise ValueError('Tracklet count does not match the manifest')
            track_ids = {t['tracklet_id'] for t in tracks}
            track_map = {t['tracklet_id']: t for t in tracks}
            if len(track_ids) != len(tracks):
                raise ValueError('Duplicate tracklet IDs')
            seen = set()
            records = []
            (staging / 'arrays').mkdir()
            (staging / 'media').mkdir()
            for i, row in enumerate(windows):
                wid = row.get('id')
                if not isinstance(wid, str) or not 1 <= len(wid) <= 200 or wid in seen:
                    raise ValueError('Missing or duplicate window ID')
                seen.add(wid)
                start, end = row.get('start'), row.get('end')
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)) or start < 0 or abs(end-start-2) > 1e-4:
                    raise ValueError('Expected finite two-second window intervals')
                if row.get('tracklet_id') not in track_ids or row.get('samples') != 50 or row.get('sample_rate') != 25:
                    raise ValueError('Invalid parent tracklet or window sample configuration')
                parent = track_map[row['tracklet_id']]
                if 'start' in parent and 'end' in parent and (start < parent['start'] - 1e-5 or end > parent['end'] + 1e-5):
                    raise ValueError('Window exceeds the exported reviewed tracklet interval')
                if row.get('array') not in names or not str(row['array']).endswith('.npz') or z.getinfo(row['array']).file_size > 4*1024**2:
                    raise ValueError('Window array is missing or too large')
                payload = z.read(row['array'])
                arrays = load_arrays(payload, row)
                if not np.allclose(arrays['source_frame_indices'], np.rint(arrays['source_times']*source['fps']), atol=0, rtol=0):
                    raise ValueError('Original frame indices do not match source FPS')
                local_id = f'w_{i:05d}'
                (staging / 'arrays' / f'{local_id}.npz').write_bytes(payload)
                media = None
                if row.get('video'):
                    if row['video'] not in names or not str(row['video']).endswith('.mp4'):
                        raise ValueError('Referenced window video is missing or unsupported')
                    media = f'{local_id}.mp4'
                    with z.open(row['video']) as src, (staging / 'media' / media).open('wb') as dst:
                        shutil.copyfileobj(src, dst)
                if row.get('flags') is not None and (not isinstance(row['flags'], list) or any(not isinstance(x,str) for x in row['flags'])):
                    raise ValueError('Window quality flags must be a list of strings')
                record = {k: row.get(k) for k in ('tracklet_id', 'shot_id', 'review_source', 'pose_provenance', 'pose_model', 'flags')}
                record.update(id=local_id, original_id=wid, start=float(start), end=float(end),
                              media=media, dataset_id=identity, source_hash=sha,
                              **describe(arrays, row))
                records.append(record)
                progress(f'Checking window {i+1} of {len(windows)}', (i+1)/len(windows)*.9)
        intervals = interval_union([[w['start'], w['end']] for w in records])
        observed = sum(b-a for a, b in intervals)
        usable = interval_union([[w['start'], w['end']] for w in records if w['quality']['usable']])
        duration = source.get('duration')
        duration = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= max(w['end'] for w in records) else None
        record = dict(id=identity, created=time.time(), filename=filename[:200], archive_sha256=file_hash,
                      feature_version=VERSION,
                      match=str(manifest.get('match', 'Unnamed source'))[:200], player=str(manifest.get('target_player', 'Unknown player'))[:100],
                      source={k:source[k] for k in ('sha256', 'width', 'height', 'fps', 'duration') if k in source}, snapshot_signature=manifest.get('snapshot_signature'),
                      window_build_signature=manifest.get('window_build_signature'), windows=records,
                      coverage={'intervals': intervals, 'observed_seconds': round(observed, 3),
                                'usable_seconds': round(sum(b-a for a, b in usable), 3),
                                'source_duration': duration, 'fraction': observed/duration if duration else None},
                      window_count=len(records), usable_count=sum(w['quality']['usable'] for w in records),
                      media_count=sum(bool(w['media']) for w in records))
        destination = store.path('datasets', identity)
        with store.lock:
            if destination.exists() and not (destination / 'record.json').is_file():
                # Recover only this hash-addressed, incomplete import after a crash.
                shutil.rmtree(destination)
            if not destination.exists():
                staging.replace(destination)
                store.write('datasets', identity, record)
        return {'dataset_id': identity, 'already_imported': False}
    except (zipfile.BadZipFile, KeyError, TypeError, AttributeError, OverflowError) as e:
        raise ValueError('Invalid Touchline export: check its manifest, window metadata and ZIP contents') from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        upload_path.unlink(missing_ok=True)
