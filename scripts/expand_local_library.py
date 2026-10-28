#!/usr/bin/env python3
"""Resume the local seven-half library expansion; default is a read-only plan.

This developer utility uses this workspace's saved jobs and existing model. It
does not run tracking, download models, modify Touchline, or contact a cloud.
Old datasets/analyses remain immutable. See docs/FULL_LIBRARY.md.
"""
import argparse
from contextlib import contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / 'scripts')]
from movement_lens.analysis import analyse
from movement_lens.features import JOINTS, describe
from movement_lens.importer import import_dataset, load_arrays
from movement_lens.store import Store, digest, sha_file
from prepare_local_demo import rebuild, source_frame_bounds

VERSION = 'full-local-library-v1'
EXPAND = {'86bdfbcf7530f21f': 'H1 first half',
          '922ae0e40eb742d4': 'H2 first half',
          'bc793d8f87950bf7': 'E02 second half'}
SECOND = {'2925bba8eea01e02': 'H1 second half',
          'd1af9e4b31f1c51b': 'H2 second half'}
H3 = {'1d4d671f8527d1dc': 'H3 first half',
      '7ca6f1e9c7413a06': 'H3 second half'}


def read(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.partial')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False))
    temp.replace(path)


def candidates(windows):
    """All greedy nonoverlapping intervals per tracklet, with no sample cap."""
    selected, ends = [], {}
    for row in sorted(windows, key=lambda w: (w['tracklet_id'], w['start'], w['id'])):
        if row['start'] >= ends.get(row['tracklet_id'], -1) - 1e-6:
            selected.append(row)
            ends[row['tracklet_id']] = row['end']
    return selected


def make_plan(project, state):
    active = read(state / 'prepared/active-demo.json')
    tasks = []
    for jid, label in EXPAND.items():
        entry = next(x for x in active['datasets'] if x['job_id'] == jid)
        dataset = read(state / 'datasets' / entry['dataset_id'] / 'record.json')
        cfg = read(project / 'runtime/jobs' / jid / 'run_config.json')
        manifest = read(project / 'touchline/runtime/jobs' / jid / 'windows/manifest.json')
        if dataset['source']['sha256'] != cfg['input_hash']:
            raise ValueError(f'{label}: active dataset/source mismatch')
        selected = candidates(manifest['windows'])
        old = {w['original_id']: w for w in dataset['windows']}
        reused = sum(w['id'] in old and reusable(old[w['id']], w, cfg['input_hash']) for w in selected)
        tasks.append(dict(job_id=jid, label=label, entry=entry, dataset=dataset, job=cfg,
                          manifest=manifest, selected=selected, old=old, reused=reused,
                          new_candidates=len(selected)-reused))
    audited = []
    for group, directory in [(SECOND, state/'second-half-references'), (H3, state/'h3-reference')]:
        for jid, label in group.items():
            entry = next(x for x in active['datasets'] if x['job_id'] == jid)
            ds = read(state/'datasets'/entry['dataset_id']/'record.json')
            if jid in SECOND:
                m = read(project/'touchline/runtime/jobs'/jid/'windows/manifest.json')
                expected = [w['id'] for w in candidates(m['windows'])]
            else:
                review = read(project/'docs/reviews/2026-10-27-h3/quality-review.json')
                expected = [w['window_id'] for w in review['nonoverlapping_candidates'] if w['job_id'] == jid]
            missing = [wid for wid in expected if not (directory/f'{wid}.json').is_file()]
            if missing:
                raise ValueError(f'{label}: prior expansion has {len(missing)} missing checkpoints; investigate before continuing')
            outcomes = [read(directory/f'{wid}.json') for wid in expected]
            accounted = all(x.get('source_hash_checked') and x.get('status') in
                            {'prepared', 'withheld', 'withheld_identity'} for x in outcomes)
            if not accounted:
                raise ValueError(f'{label}: prior expansion has unverified/incomplete outcomes')
            prepared = {x['original_id'] for x in outcomes if x['status'] == 'prepared'}
            if prepared != {w['original_id'] for w in ds['windows']}:
                raise ValueError(f'{label}: imported windows do not account for completed preparation')
            audited.append(dict(job_id=jid, label=label, candidates=len(expected),
                                imported=ds['window_count'], usable=ds['usable_count'],
                                status='all prior candidates accounted for; preserved'))
    return active, tasks, audited


def reusable(old, row, source_hash, model_tag=None):
    return (old.get('source_hash') == source_hash and old.get('tracklet_id') == row['tracklet_id']
            and abs(old['start']-row['start']) < 1e-6 and abs(old['end']-row['end']) < 1e-6
            and old.get('pose_provenance') == 'source_bound_recomputed' and old.get('media')
            and (model_tag is None or old.get('pose_model') == model_tag))


def exported_row(row, match, model_tag, old=None):
    result = {k: row.get(k) for k in ('id', 'tracklet_id', 'shot_id', 'start', 'end')}
    result.update(samples=50, sample_rate=25, array=f'windows/{row["id"]}.npz',
                  video=f'windows/{row["id"]}.mp4', match=match,
                  pose_provenance='source_bound_recomputed', pose_model=model_tag,
                  review_source=(old or row).get('review_source') or 'imported_unspecified',
                  flags=sorted(set((row.get('flags') or []) + ((old or {}).get('flags') or []))))
    return result


def probe_media(path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        n, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
        first, _ = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n-1))
        last, _ = cap.read()
        return n, fps, bool(first and last)
    finally:
        cap.release()


def copy_media(source, destination):
    n, fps, ok = probe_media(source)
    if not ok or abs(fps-25) > 1e-4 or n not in (50, 51):
        raise ValueError(f'Unexpected source clip frame count/FPS: {source.name}')
    if n == 50:
        shutil.copyfile(source, destination)
    else:
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                        '-frames:v', '50', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-an', str(destination)], check=True)
    verify_media(destination)


def verify_media(path):
    n, fps, ok = probe_media(path)
    if not ok or n != 50 or abs(fps-25) > 1e-4:
        raise ValueError('Prepared clip must decode as 50 frames at 25 FPS')


def checkpoint_valid(record, fingerprint, directory):
    if record.get('fingerprint') != fingerprint:
        return False
    if record.get('status') == 'withheld':
        return True
    if record.get('status') != 'prepared':
        return False
    for name, expected in record['artifact_sha256'].items():
        path = directory/name
        if not path.is_file() or sha_file(path) != expected:
            return False
    return True


def prepare_one(task, row, state, directory, fingerprint, model_tag, get_model, cap):
    """Checkpoint only complete, validated artifacts. Resume checks their hashes."""
    directory.mkdir(parents=True, exist_ok=True)
    base = directory/row['id']
    record_path = base.with_suffix('.json')
    if record_path.is_file():
        saved = read(record_path)
        if checkpoint_valid(saved, fingerprint, directory):
            return saved, 'checkpoint'
    old = task['old'].get(row['id'])
    can_reuse = old and reusable(old, row, task['job']['input_hash'], model_tag)
    # A changed model can require fresh poses without erasing an earlier identity
    # exclusion. Stable source/track/time identifies which review still applies.
    review = old if old and reusable(old, row, task['job']['input_hash']) else None
    new = exported_row(row, task['dataset']['match'], model_tag, review)
    array_path, video_path = base.with_suffix('.npz'), base.with_suffix('.mp4')
    if can_reuse:
        parent = state/'datasets'/task['dataset']['id']
        payload = (parent/'arrays'/f'{old["id"]}.npz').read_bytes()
        arrays = load_arrays(payload, new)
        array_path.write_bytes(payload)
        copy_media(parent/'media'/old['media'], video_path)
        origin = 'reused_verified_dataset'
    else:
        original = task['touchline_runtime']/row['array_path']
        arrays = load_arrays(original.read_bytes(), row)
        arrays, frames = rebuild(get_model(), cap, arrays, task['job']['fps'], 'cpu')
        if arrays is None:
            # A disconnected/unreadable drive is a resumable failure, not a
            # permanent negative pose result for all remaining candidates.
            if not Path(task['job']['path']).is_file():
                raise ValueError('Source drive disconnected; completed checkpoints are retained')
            import cv2
            cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_bounds(row['start'], task['job']['fps'])[0])
            decoded, _ = cap.read()
            if not decoded:
                raise ValueError('Source frames are unreadable; reconnect the drive and resume')
            saved = dict(fingerprint=fingerprint, status='withheld', original_id=row['id'],
                         reason='No adequately matched source-bound pose or source frames', source_hash_checked=True)
            atomic_json(record_path, saved)
            return saved, 'withheld'
        np.savez_compressed(array_path, **arrays)
        import cv2
        raw = base.with_suffix('.raw.mp4')
        writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*'mp4v'), 25, (256, 512))
        if not writer.isOpened():
            raise ValueError('Cannot create temporary clip')
        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(raw),
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-an', str(video_path)], check=True)
        verify_media(video_path)
        raw.unlink()
        load_arrays(array_path.read_bytes(), new)
        origin = 'recomputed_exact_source'
    saved = dict(fingerprint=fingerprint, status='prepared', original_id=row['id'], row=new,
                 source_hash_checked=True, origin=origin, quality=describe(arrays, new)['quality'],
                 artifact_sha256={p.name: sha_file(p) for p in (array_path, video_path)})
    atomic_json(record_path, saved)
    return saved, origin


def package(task, outcomes, directory, model_hash, reference):
    rows = [copy.deepcopy(x['row']) for x in outcomes if x['status'] == 'prepared']
    if not rows:
        raise ValueError(f'{task["label"]}: no prepared windows')
    # Keep the review/quality exclusions inspectable. Avoid double-counted source
    # observations across different tracklet IDs in the reference collection.
    if reference:
        end = -1.
        for row in sorted(rows, key=lambda w: (w['start'], w['id'])):
            a = load_arrays((directory/f'{row["id"]}.npz').read_bytes(), row)
            if not describe(a, row)['quality']['usable']:
                continue
            if row['start'] < end-1e-6:
                row['flags'] = sorted(set(row['flags'] + ['review_excluded']))
            else:
                end = row['end']
    cfg = task['job']
    signature = digest([VERSION, cfg['input_hash'], model_hash, task['manifest']['signature'], rows])
    path = directory/f'{task["job_id"]}-{signature[:16]}.zip'
    if path.is_file():
        with zipfile.ZipFile(path) as z:
            if json.loads(z.read('manifest.json'))['snapshot_signature'] != signature:
                raise ValueError('Existing bundle signature mismatch')
        return path
    tracks = [dict(tracklet_id=tid, start=min(w['start'] for w in rows if w['tracklet_id'] == tid),
                   end=max(w['end'] for w in rows if w['tracklet_id'] == tid)) for tid in sorted({w['tracklet_id'] for w in rows})]
    manifest = dict(schema_version=1, created=time.time(), mode='windows', job_id=task['job_id'],
                    match=task['dataset']['match'], target_player=cfg['target'], timestamp_basis='original_source_seconds',
                    intervals='[start,end)', keypoint_order=JOINTS,
                    source={k: cfg[k] for k in ('width', 'height', 'fps', 'duration')} |
                           {'sha256': cfg['input_hash'], 'filename': Path(cfg['path']).name},
                    models={'pose_sha256': model_hash}, snapshot_signature=signature,
                    window_build_signature=task['manifest']['signature'], window_count=len(rows),
                    tracklet_count=len(tracks), included_video=True,
                    preparation={'version': VERSION, 'sampling': 'all greedy nonoverlapping candidates per tracklet; no demo cap',
                                 'source_hash_checked': True, 'identity': 'Existing review provenance/flags preserved; new identities not independently certified'})
    temp = path.with_suffix('.partial')
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
        for row in rows:
            z.write(directory/f'{row["id"]}.npz', row['array'])
            z.write(directory/f'{row["id"]}.mp4', row['video'])
        for name, value in [('manifest.json', manifest), ('windows.json', rows), ('tracklets.json', tracks)]:
            z.writestr(name, json.dumps(value, allow_nan=False))
    temp.replace(path)
    return path


def activate(state, previous, replacements, store):
    active_path = state/'prepared/active-demo.json'
    if read(active_path) != previous:
        raise ValueError('Active workspace changed during preparation; retained outputs, but did not change its pointer')
    updated = copy.deepcopy(previous)
    for task, dataset in replacements:
        old_id = task['entry']['dataset_id']
        item = task['entry'] | dict(dataset_id=dataset['id'], windows=dataset['window_count'], usable=dataset['usable_count'])
        updated['datasets'] = [item if x['job_id'] == task['job_id'] else x for x in updated['datasets']]
        updated['reference_ids'] = [dataset['id'] if x == old_id else x for x in updated['reference_ids']]
        if updated['query_id'] == old_id:
            updated['query_id'] = dataset['id']
    result = analyse(store, updated['query_id'], updated['reference_ids'])
    updated.update(analysis_id=result['analysis_id'], previous_analysis_id=previous['analysis_id'],
                   expansion={'version': VERSION, 'selection': 'all available nonoverlapping candidates; quality gates retained',
                              'identity_note': 'New windows preserve upstream review provenance; no new identity certification'})
    # Recheck after analysis too; no partial activation if comparison failed.
    if read(active_path) != previous:
        raise ValueError('Active workspace changed while comparing; did not activate the new analysis')
    atomic_json(active_path, updated)
    return updated


@contextmanager
def single_run(path):
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another expansion is already running') from None
        yield


def execute(project, state, checkpoint):
    import cv2
    if not checkpoint.is_file() or not shutil.which('ffmpeg'):
        raise ValueError('Existing local pose checkpoint and ffmpeg are required; nothing will be downloaded')
    output = state/'full-library-expansion'
    output.mkdir(parents=True, exist_ok=True)
    with single_run(output/'run.lock'):
        previous, tasks, audited = make_plan(project, state)
        if not (output/'previous-active-demo.json').exists():
            atomic_json(output/'previous-active-demo.json', previous)
        preserved = {str(p): sha_file(p) for kind in ('datasets', 'analyses')
                     for p in (state/kind).glob('*/record.json')}
        model_hash = sha_file(checkpoint)
        model_tag = 'yolov8x-pose:384:' + model_hash[:16]
        helper_hash = sha_file(APP/'scripts/prepare_local_demo.py')
        os.environ['YOLO_CONFIG_DIR'] = str(output/'ultralytics')
        model = None

        def get_model():
            nonlocal model
            if model is None:
                from ultralytics import YOLO
                model = YOLO(str(checkpoint))
            return model

        replacements, statistics = [], []
        started = time.monotonic()
        store = Store(state)
        for task in tasks:
            cfg = task['job']
            source = Path(cfg['path'])
            print(f'\n{task["label"]}: checking exact source SHA-256', flush=True)
            if not source.is_file() or sha_file(source) != cfg['input_hash']:
                raise ValueError(f'{task["label"]}: missing/mismatched source video; reconnect the expected drive')
            if abs(cfg['fps']-25) > 1e-4:
                raise ValueError('This local migration expects the verified 25 FPS sources')
            task['touchline_runtime'] = project/'touchline/runtime'
            key = digest([VERSION, cfg['input_hash'], model_hash, helper_hash, task['manifest']['signature']])
            directory = output/task['job_id']/key[:16]
            outcomes = []
            cap = cv2.VideoCapture(str(source))
            if not cap.isOpened():
                raise ValueError('Cannot open verified source video')
            try:
                for i, row in enumerate(task['selected'], 1):
                    old = task['old'].get(row['id'], {})
                    fingerprint = digest([key, {k: row.get(k) for k in ('id', 'tracklet_id', 'start', 'end', 'flags', 'review_source')},
                                          {k: old.get(k) for k in ('flags', 'review_source')}])
                    result, origin = prepare_one(task, row, state, directory, fingerprint, model_tag, get_model, cap)
                    outcomes.append(result)
                    progress = dict(label=task['label'], completed=i, candidates=len(task['selected']),
                                    last_window=row['id'], last_result=origin, elapsed_seconds=round(time.monotonic()-started, 1))
                    atomic_json(output/'progress.json', progress)
                    print(f'{task["label"]} {i}/{len(task["selected"])}: {origin}', flush=True)
            finally:
                cap.release()
            bundle = package(task, outcomes, directory, model_hash, task['job_id'] != 'bc793d8f87950bf7')
            upload = directory/'import-copy.zip'
            shutil.copyfile(bundle, upload)
            result = import_dataset(store, upload, bundle.name)
            ds = store.read('datasets', result['dataset_id'])
            replacements.append((task, ds))
            statistics.append(dict(job_id=task['job_id'], label=task['label'], candidates=len(outcomes),
                                   dataset_id=ds['id'], imported=ds['window_count'], usable=ds['usable_count'],
                                   withheld_before_import=sum(x['status'] != 'prepared' for x in outcomes),
                                   reused_verified=sum(x.get('origin') == 'reused_verified_dataset' for x in outcomes),
                                   bundle=str(bundle)))
            atomic_json(output/'completed-subsets.json', statistics)
        if any(not Path(path).is_file() or sha_file(path) != expected for path, expected in preserved.items()):
            raise ValueError('An existing dataset/analysis record changed; new outputs retained, activation stopped')
        updated = activate(state, previous, replacements, store)
        analysis = store.read('analyses', updated['analysis_id'])
        summary = dict(version=VERSION, expanded=statistics, preserved=audited,
                       analysis_id=updated['analysis_id'], reference_count=analysis['reference_count'], query_count=analysis['query_count'],
                       previous_records_unchanged=True, elapsed_minutes=round((time.monotonic()-started)/60, 2),
                       url=f'http://127.0.0.1:8770/?analysis={updated["analysis_id"]}&view=episodes')
        atomic_json(output/'summary.json', summary)
        print('\nCompleted. Previous datasets and analyses preserved.\n'+json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Prepare, import and activate expanded snapshots; default only prints the plan')
    parser.add_argument('--project', type=Path, default=APP.parent)
    parser.add_argument('--state', type=Path, default=Path(os.environ.get('MOVEMENT_LENS_STATE', APP/'runtime')))
    args = parser.parse_args()
    project, state = args.project.resolve(), args.state.resolve()
    _, tasks, audited = make_plan(project, state)
    print('No demo sampling cap. Overlapping windows and quality exclusions remain explicit.')
    for t in tasks:
        print(f'{t["label"]}: {len(t["manifest"]["windows"])} cached → {len(t["selected"])} nonoverlapping candidates; '
              f'{t["reused"]} existing source-bound candidates; about {t["new_candidates"]} new')
    for item in audited:
        print(f'{item["label"]}: {item["candidates"]} prior candidates accounted for, {item["usable"]} usable imported; preserve')
    print(f'Total new candidates: {sum(t["new_candidates"] for t in tasks)}. Budget approximately 45–75 minutes overall on this machine.')
    if args.run:
        execute(project, state, project/'models/yolov8x-pose.pt')
    else:
        print('Plan only: no inference, imports, source hashing, cloud calls or state changes. Add --run to execute.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped. Completed checkpoints retained; rerun the same command to resume.', file=sys.stderr)
        sys.exit(130)
