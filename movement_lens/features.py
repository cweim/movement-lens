"""Projected 2D descriptors with explicit joint validity and real time axes."""
import numpy as np

VERSION = 'projected-2d-16-v1'
JOINTS = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder', 'right_shoulder',
          'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist', 'left_hip', 'right_hip', 'left_knee',
          'right_knee', 'left_ankle', 'right_ankle']
BONES = [[5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16]]
FEATURES = [f'{side}_{joint}_{stat}' for joint in ('knee', 'hip') for side in ('left', 'right')
            for stat in ('p10', 'median', 'p90')] + ['trunk_median', 'trunk_iqr', 'ankle_separation_median', 'ankle_separation_iqr']
LABELS = {f'{side}_{joint}_{stat}': f'{side.title()} projected {joint} {stat}' for joint in ('knee', 'hip')
          for side in ('left', 'right') for stat in ('p10', 'median', 'p90')}
LABELS.update(trunk_median='Projected trunk inclination median', trunk_iqr='Projected trunk inclination IQR',
              ankle_separation_median='Torso-scaled ankle separation median', ankle_separation_iqr='Torso-scaled ankle separation IQR')


def interval_union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1e-7:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([float(start), float(end)])
    return merged


def describe(arrays, row):
    p = arrays['keypoints'].astype(float)
    valid = arrays['valid_mask'].astype(bool) & (arrays['kp_conf'] >= .3) & np.isfinite(p).all(axis=2)
    confidence_fraction = float(valid[:, 11:17].mean())
    source_times = arrays['source_times']
    reasons = []
    for flag in row.get('flags', []) or []:
        if flag in {'identity_ambiguous', 'review_excluded', 'camera_cut'}:
            reasons.append('Withheld by source review: ' + flag.replace('_', ' '))
    if len(source_times) < 10:
        reasons.append('Fewer than ten original pose observations')
    if np.diff(source_times).max(initial=0) > .40001:
        reasons.append('Original pose gap exceeds 0.4 seconds')
    if source_times[0] - row['start'] > .12001 or row['end'] - source_times[-1] > .12001:
        reasons.append('Incomplete original pose coverage at window boundary')
    original_visibility = arrays['observed_keypoints'][:, :, 2] >= .3
    required_original = original_visibility[:, [5, 6, 11, 12, 13, 14, 15, 16]].mean(axis=0)
    if np.any(required_original < .8):
        reasons.append('Less than 80% required-joint visibility in original observations')
    vectors, traces = {}, {}

    def record(name, vals, mask, stats=('p10', 'median', 'p90')):
        vals = np.where(mask & np.isfinite(vals), vals, np.nan)
        traces[name] = [round(float(x), 4) if np.isfinite(x) else None for x in vals]
        if np.isfinite(vals).mean() < .8:
            reasons.append(f'Less than 80% usable samples for {name.replace("_", " ")}')
            return
        q10, q25, med, q75, q90 = np.nanpercentile(vals, [10, 25, 50, 75, 90])
        values = dict(p10=q10, median=med, p90=q90, iqr=q75-q25)
        for stat in stats:
            vectors[f'{name}_{stat}'] = float(values[stat])

    for name, (a, b, c) in {'left_knee': (11, 13, 15), 'right_knee': (12, 14, 16),
                             'left_hip': (5, 11, 13), 'right_hip': (6, 12, 14)}.items():
        x, y = p[:, a] - p[:, b], p[:, c] - p[:, b]
        denom = np.linalg.norm(x, axis=1) * np.linalg.norm(y, axis=1)
        angles = np.degrees(np.arccos(np.clip((x*y).sum(1) / np.maximum(denom, 1e-9), -1, 1)))
        record(name, angles, valid[:, a] & valid[:, b] & valid[:, c] & (denom > 1e-8))
    hips = (p[:, 11] + p[:, 12]) / 2
    shoulders = (p[:, 5] + p[:, 6]) / 2
    torso = shoulders - hips
    scale = (np.linalg.norm(p[:, 5] - p[:, 11], axis=1) + np.linalg.norm(p[:, 6] - p[:, 12], axis=1)) / 2
    body_ok = valid[:, [5, 6, 11, 12]].all(1) & (scale >= 5)
    record('trunk', np.degrees(np.arctan2(torso[:, 0], -torso[:, 1])), body_ok, ('median', 'iqr'))
    record('ankle_separation', np.linalg.norm(p[:, 15] - p[:, 16], axis=1) / np.maximum(scale, 1),
           body_ok & valid[:, 15] & valid[:, 16], ('median', 'iqr'))

    # Bone-length discontinuity is a quality signal, never unusual-movement evidence.
    for a, b in [(11, 13), (13, 15), (12, 14), (14, 16)]:
        lengths = np.linalg.norm(p[:, a] - p[:, b], axis=1)
        pairs = valid[:, a] & valid[:, b]
        baseline = np.median(lengths[pairs]) if pairs.any() else 0
        if baseline > 0 and np.any((np.abs(np.diff(lengths)) > baseline * .75) & pairs[1:] & pairs[:-1]):
            reasons.append('Large frame-to-frame projected limb-length change')
            break
    provenance = row.get('pose_provenance', 'unspecified')
    source_bound = provenance in {'source_bound', 'source_bound_recomputed', 'verified_source_binding'}
    if not source_bound:
        reasons.append('Pose-to-source binding is unverified')
    usable = len(vectors) == len(FEATURES) and not reasons
    quality = {'usable': usable, 'status': 'usable' if usable else 'withheld', 'reasons': list(dict.fromkeys(reasons)),
               'joint_valid_fraction': round(confidence_fraction, 4), 'source_observations': len(source_times),
               'interpolated_fraction': round(float(arrays['interpolated'].mean()), 4),
               'minimum_original_joint_visibility': round(float(required_original.min()), 4),
               'source_binding': 'declared_source_bound' if source_bound else 'unverified',
               'identity_provenance': row.get('review_source', 'unspecified')}
    return {'features': vectors, 'quality': quality, 'traces': traces}
