"""Frozen reference-only scaling, neighbor comparisons and distinct episodes."""
import re
import time

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

from .features import FEATURES, LABELS, VERSION, interval_union
from .store import digest

K = 10


def nonoverlapping(windows):
    chosen, ends = [], {}
    for w in sorted(windows, key=lambda x: (x['source_hash'], str(x['tracklet_id']), x['start'])):
        group = w['source_hash'], w['tracklet_id']
        if w['start'] >= ends.get(group, -1) - 1e-6:
            chosen.append(w)
            ends[group] = w['end']
    return chosen


def source_groups(dataset):
    # A display label may identify the source half; both halves share one split.
    match = re.sub(r'\s*·\s*(?:first|second)(?: source)? half\s*$', '',
                   dataset['match'].strip().casefold()).strip()
    return {dataset['source']['sha256'], 'match:' + match}


def analyse(store, query_id, reference_ids, calibration_id=None, progress=lambda *_: None):
    reference_ids = sorted(set(reference_ids))
    if not reference_ids:
        raise ValueError('Choose at least one separate reference dataset')
    if query_id in reference_ids or calibration_id in [query_id, *reference_ids]:
        raise ValueError('Query, reference and calibration datasets must be separate')
    query = store.read('datasets', query_id)
    references = [store.read('datasets', x) for x in reference_ids]
    calibration = store.read('datasets', calibration_id) if calibration_id else None
    if any(d.get('feature_version') != VERSION for d in [query, *references] + ([calibration] if calibration else [])):
        raise ValueError('Reimport the original ZIP to update its descriptors and quality checks before analysis')
    for other in references + ([calibration] if calibration else []):
        if other['player'].strip().casefold() != query['player'].strip().casefold():
            raise ValueError('Choose reference and calibration datasets for the same player')
        if source_groups(query) & source_groups(other):
            raise ValueError('A query match/source cannot also be a reference or calibration match')
    if calibration and any(source_groups(calibration) & source_groups(r) for r in references):
        raise ValueError('Calibration must use a different match/source from reference fitting')
    identity = 'a_' + digest([VERSION, query_id, reference_ids, calibration_id, K])[:24]
    try:
        store.read('analyses', identity)
        return {'analysis_id': identity, 'cached': True}
    except KeyError:
        pass
    progress('Selecting usable reference windows', .1)
    ref = nonoverlapping([w for d in references for w in d['windows'] if w['quality']['usable']])
    # Re-exports and duplicated half datasets cannot count the same observations twice.
    unique = {}
    for w in ref:
        unique[(w['source_hash'], w['tracklet_id'], w['start'], w['end'])] = w
    ref = list(unique.values())
    if len(ref) < K:
        raise ValueError(f'Need at least {K} usable, non-overlapping reference windows; found {len(ref)}. Unverified source caches are withheld.')
    usable_queries = [w for w in query['windows'] if w['quality']['usable']]
    if not usable_queries:
        raise ValueError('No query windows pass source-binding and pose checks. Browse the quality reasons before analysis.')
    X = np.array([[w['features'][f] for f in FEATURES] for w in ref])
    med = np.median(X, axis=0)
    spread = np.percentile(X, 75, axis=0) - np.percentile(X, 25, axis=0)
    kept = spread > 1e-6
    if kept.sum() < 2:
        raise ValueError('Reference movements have too little descriptor variation for a useful comparison')
    scaler = RobustScaler().fit(X[:, kept])
    scaled = scaler.transform(X[:, kept])
    nn = NearestNeighbors(n_neighbors=K).fit(scaled)
    names = [f for f, take in zip(FEATURES, kept) if take]

    def transform(windows):
        return scaler.transform(np.array([[w['features'][f] for f in names] for w in windows]))

    progress('Checking separate calibration support', .35)
    cal_windows = nonoverlapping([w for w in calibration['windows'] if w['quality']['usable']]) if calibration else []
    cal_tracklets = len({w['tracklet_id'] for w in cal_windows})
    calibrated = len(cal_windows) >= 30 and cal_tracklets >= 5
    cal_scores = nn.kneighbors(transform(cal_windows))[0].mean(1) if calibrated else np.array([])
    cal_record = {'dataset_id': calibration_id, 'windows': len(cal_windows), 'tracklets': cal_tracklets,
                  'available': calibrated, 'state': 'empirical_reference_rank' if calibrated else 'uncalibrated',
                  'message': ('Ranks use separate calibration observations; they are not event probabilities.' if calibrated else
                              'Distance ranking only. Calibration requires at least 30 non-overlapping usable windows across five tracklets in a separate match.')}
    progress('Finding nearest reference examples', .5)
    Z = transform(usable_queries)
    distances, indices = nn.kneighbors(Z, n_neighbors=min(len(ref), 60))
    scored = []
    for row_index, w in enumerate(usable_queries):
        ds, ix = distances[row_index], indices[row_index]
        raw = float(ds[:K].mean())
        percentile = float((cal_scores <= raw).mean()) if calibrated else None
        comparisons, seen_tracks = [], set()
        for distance, idx in zip(ds, ix):
            other = ref[int(idx)]
            key = other['source_hash'], other['tracklet_id']
            if key in seen_tracks:
                continue
            seen_tracks.add(key)
            delta = {f: float(w['features'][f] - other['features'][f]) for f in names}
            ordered = sorted(names, key=lambda f: abs(delta[f]/scaler.scale_[names.index(f)]), reverse=True)
            comparisons.append({'dataset_id': other['dataset_id'], 'window_id': other['id'], 'original_id': other['original_id'],
                                'start': other['start'], 'distance': float(distance),
                                'differences': [{'feature': f, 'label': LABELS[f], 'query': w['features'][f], 'reference': other['features'][f],
                                                 'difference': delta[f]} for f in ordered[:6]]})
            if len(comparisons) == 3:
                break
        scored.append({'window_id': w['id'], 'original_id': w['original_id'], 'tracklet_id': w['tracklet_id'], 'shot_id': w['shot_id'],
                       'start': w['start'], 'end': w['end'], 'distance': raw, 'percentile': percentile, 'comparisons': comparisons})
    progress('Merging overlapping windows into episodes', .8)
    # Cluster temporal windows only within the same tracked shot; retain all ranks.
    episodes = []
    for w in sorted(scored, key=lambda x: (str(x['tracklet_id']), str(x['shot_id']), x['start'])):
        eligible = (w['percentile'] is not None and w['percentile'] >= .95)
        if (episodes and episodes[-1]['tracklet_id'] == w['tracklet_id'] and episodes[-1]['shot_id'] == w['shot_id']
                and w['start'] < episodes[-1]['end'] - 1e-6 and episodes[-1]['above_review_threshold'] == eligible):
            e = episodes[-1]
            e['end'] = max(e['end'], w['end'])
            e['members'].append(w['window_id'])
            if w['distance'] > e['distance']:
                e.update(distance=w['distance'], percentile=w['percentile'], window_id=w['window_id'], comparisons=w['comparisons'])
        else:
            episodes.append({'id': 'e_' + digest([identity, w['tracklet_id'], w['start']])[:16],
                             'tracklet_id': w['tracklet_id'], 'shot_id': w['shot_id'], 'start': w['start'], 'end': w['end'],
                             'window_id': w['window_id'], 'members': [w['window_id']], 'distance': w['distance'],
                             'percentile': w['percentile'], 'above_review_threshold': eligible, 'comparisons': w['comparisons']})
    episodes.sort(key=lambda e: e['distance'], reverse=True)
    for i, e in enumerate(episodes):
        e['rank'] = i + 1
    result = {'id': identity, 'created': time.time(), 'version': VERSION, 'query_id': query_id,
              'reference_ids': reference_ids, 'calibration': cal_record, 'reference_count': len(ref),
              'reference_tracklets': len({(w['source_hash'], w['tracklet_id']) for w in ref}), 'query_count': len(scored),
              'withheld_count': query['window_count']-len(scored), 'feature_names': names,
              'model': {'scaler_center': scaler.center_.tolist(), 'scaler_scale': scaler.scale_.tolist(), 'k': K,
                        'reference_feature_medians': {f: float(v) for f, v in zip(FEATURES, med)},
                        'reference_window_ids': [{'dataset_id': w['dataset_id'], 'window_id': w['id']} for w in ref]},
              'scores': scored, 'episodes': episodes,
              'limitations': ['Projected 2D descriptors remain sensitive to camera viewpoint.',
                              'Ranks describe this selected reference library, not injury or fatigue probability.',
                              'Unobserved footage cannot establish what the player was doing.',
                              'Identity-review provenance is retained; source binding does not validate player identity.']}
    store.write('analyses', identity, result)
    return {'analysis_id': identity, 'cached': False}


def evidence(store, analysis_id, episode_id):
    analysis = store.read('analyses', analysis_id)
    episode = next((e for e in analysis['episodes'] if e['id'] == episode_id), None)
    if episode is None:
        raise KeyError('Episode not found')
    query = store.read('datasets', analysis['query_id'])
    window = next(w for w in query['windows'] if w['id'] == episode['window_id'])
    comparisons = []
    for c in episode['comparisons']:
        d = store.read('datasets', c['dataset_id'])
        w = next(w for w in d['windows'] if w['id'] == c['window_id'])
        comparisons.append(c | {'window': w, 'match': d['match']})
    return {'analysis_id': analysis_id, 'episode': episode, 'query': {'dataset_id': query['id'], 'match': query['match'],
            'player': query['player'], 'coverage': query['coverage'], 'window': window}, 'comparisons': comparisons,
            'reference_count': analysis['reference_count'], 'calibration': analysis['calibration'], 'limitations': analysis['limitations']}


def explain(bundle, audience='analyst', question=''):
    e, w = bundle['episode'], bundle['query']['window']
    diff = bundle['comparisons'][0]['differences'] if bundle['comparisons'] else []
    if any(term in question.casefold() for term in ('injury', 'injured', 'diagnos', 'fatigue', 'risk', 'safe', 'sprint', 'speed')):
        intro = 'This evidence does not establish injury, fatigue, physical speed or player safety. It supports inspection of projected movement differences only.'
    else:
        intro = ('This episode differs from the selected reference movements. Compare the real clips and traces before interpreting the difference.' if audience == 'viewer' else
                 f'The representative window has mean ten-neighbor distance {e["distance"]:.3f} against {bundle["reference_count"]} eligible reference windows.')
    facts = [{'text': f'{d["label"]}: {d["query"]:.2f} in the query versus {d["reference"]:.2f} in the closest example.',
              'evidence_ids': [w['original_id'], bundle['comparisons'][0]['original_id']]} for d in diff[:3]]
    return {'provider': 'local', 'audience': audience, 'summary': intro, 'observations': facts,
            'limitations': bundle['limitations'] + [bundle['calibration']['message']],
            'evidence_ids': [w['original_id']] + [c['original_id'] for c in bundle['comparisons']], 'tool_trace': [],
            'created': time.time()}
