"""Frozen movement catalogue, seed retrieval and source-time recurrence.

Numerical groups are anonymous. Profiles use nonoverlapping observations; search
can inspect all unique usable windows. Neither implies whole-match workload.
"""
import time
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import RobustScaler
from threadpoolctl import threadpool_limits

from .analysis import source_groups
from .features import FEATURES, LABELS, VERSION as FEATURE_VERSION, interval_union
from .research import PAPERS, REGIONS, region_for
from .store import digest

VERSION = 'movement-catalogue-v2'
LIMITATIONS = [
    'Patterns describe the selected usable footage; unobserved intervals remain unknown.',
    'Projected 2D descriptors remain sensitive to viewpoint and do not preserve full temporal order.',
    'Groups are numerical discovery aids, not validated walking/running or injury classes.',
    'Matching bouts are not steps or repetitions. Frequency does not establish muscle load, soreness or recovery needs.',
    'Source binding and technical pose eligibility do not certify player identity.',
]


def key(w):
    return f'{w["dataset_id"]}:{w["id"]}'


def seconds(intervals):
    return round(sum(b-a for a, b in interval_union(intervals)), 4)


def independent(windows):
    selected, ends = [], {}
    for w in sorted(windows, key=lambda w: (w['source_hash'], w['start'], key(w))):
        if w['start'] >= ends.get(w['source_hash'], -1)-1e-6:
            selected.append(w)
            ends[w['source_hash']] = w['end']
    return selected


def create_exploration(store, dataset_ids, reference_ids=None, clusters=None, progress=lambda *_: None):
    dataset_ids = sorted(set(dataset_ids))
    reference_ids = sorted(set(reference_ids or []))
    if not dataset_ids or not set(reference_ids) <= set(dataset_ids):
        raise ValueError('Choose datasets and a scaling library contained in that selection')
    if clusters is not None and not 2 <= clusters <= 8:
        raise ValueError('Choose between two and eight groups')
    identity = 'x_' + digest([VERSION, FEATURE_VERSION, dataset_ids, reference_ids, clusters])[:24]
    try:
        store.read('explorations', identity)
        return {'exploration_id': identity, 'cached': True}
    except KeyError:
        pass
    datasets = [store.read('datasets', did) for did in dataset_ids]
    if len({d['player'].strip().casefold() for d in datasets}) != 1:
        raise ValueError('Explore one player at a time')
    if any(d['feature_version'] != FEATURE_VERSION for d in datasets):
        raise ValueError('Reimport datasets with current descriptor/quality checks')
    progress('Collecting unique usable player windows', .1)
    unique, fit_unique, source_meta = {}, {}, {}
    # Prefer the newest selected snapshot for duplicate observations.
    for d in sorted(datasets, key=lambda d: (d['created'], d['id']), reverse=True):
        match_id = next(x for x in source_groups(d) if x.startswith('match:'))
        source_meta.setdefault(d['source']['sha256'], {'id': d['source']['sha256'], 'match': d['match'],
                                                      'match_id': match_id, 'duration': d['coverage']['source_duration']})
        for w in d['windows']:
            if not w['quality']['usable']:
                continue
            observation = (w['source_hash'], w['start'], w['end'])
            item = w | {'match': source_meta[w['source_hash']]['match'], 'match_id': source_meta[w['source_hash']]['match_id']}
            unique.setdefault(observation, item)
            if not reference_ids or d['id'] in reference_ids:
                fit_unique.setdefault(observation, item)
    windows = sorted(unique.values(), key=lambda w: (w['source_hash'], w['start'], key(w)))
    fitting = independent(list(fit_unique.values()))
    if len(fitting) < 4:
        raise ValueError('Need at least four independent usable observations in the scaling library')
    fit_x = np.array([[w['features'][f] for f in FEATURES] for w in fitting])
    keep = np.percentile(fit_x, 75, axis=0)-np.percentile(fit_x, 25, axis=0) > 1e-6
    if keep.sum() < 2:
        raise ValueError('The scaling library has too little descriptor variation')
    names = [f for f, take in zip(FEATURES, keep) if take]
    scaler = RobustScaler().fit(fit_x[:, keep])
    fit_z = scaler.transform(fit_x[:, keep])
    all_x = np.array([[w['features'][f] for f in names] for w in windows])
    all_z = scaler.transform(all_x)
    metrics, models = [], {}
    maximum = min(8, len(fitting)-1, len(np.unique(fit_z, axis=0)))
    progress('Discovering representative numerical movement groups', .35)
    with threadpool_limits(limits=1):
        for k in range(2, maximum+1):
            model = KMeans(n_clusters=k, random_state=17, n_init=10).fit(fit_z)
            if len(set(model.labels_)) != k:
                continue
            silhouette = float(silhouette_score(fit_z, model.labels_, sample_size=min(1000, len(fit_z)), random_state=17))
            metrics.append({'k': k, 'wcss': float(model.inertia_), 'silhouette': silhouette,
                            'davies_bouldin': float(davies_bouldin_score(fit_z, model.labels_)),
                            'sizes': np.bincount(model.labels_, minlength=k).tolist()})
            models[k] = model
        if not metrics or clusters is not None and clusters not in models:
            raise ValueError('Too few distinct usable movements for the requested grouping')
        chosen = clusters or max(metrics, key=lambda m: m['silhouette'])['k']
        model = models[chosen]
        labels = model.predict(all_z)
        again = KMeans(n_clusters=chosen, random_state=41, n_init=10).fit(fit_z)
        stability = float(adjusted_rand_score(model.labels_, again.labels_))
    groups = []
    for group in range(chosen):
        idx = np.where(labels == group)[0]
        ranked = sorted(idx, key=lambda i: float(np.linalg.norm(all_z[i]-model.cluster_centers_[group])))
        representatives, seen = [], set()
        for i in ranked:
            w = windows[int(i)]
            track = (w['source_hash'], w['tracklet_id'])
            if track in seen:
                continue
            representatives.append(key(w)); seen.add(track)
            if len(representatives) == 3:
                break
        groups.append({'id': group, 'name': f'Movement group {group+1}', 'count': len(idx), 'representatives': representatives})
    pool = independent(windows)
    profile_keys = {key(w) for w in pool}
    summaries = []
    for w, group in zip(windows, labels):
        summaries.append({k: w[k] for k in ('dataset_id', 'id', 'original_id', 'tracklet_id', 'source_hash', 'start', 'end', 'match', 'match_id', 'media')} |
                         {'key': key(w), 'group': int(group), 'profile_sample': key(w) in profile_keys,
                          'identity_provenance': w['quality'].get('identity_provenance', 'unspecified')})
    sources, matches = [], []
    for sha, meta in source_meta.items():
        part = [w for w in summaries if w['source_hash'] == sha]
        source_datasets = [d for d in datasets if d['source']['sha256'] == sha]
        retained = interval_union([[w['start'], w['end']] for d in source_datasets for w in d['windows']])
        sources.append(meta | {'usable_intervals': interval_union([[w['start'], w['end']] for w in part]),
                               'retained_intervals': retained, 'usable_seconds': seconds([[w['start'], w['end']] for w in part]),
                               'window_count': len(part)})
    for match_id in sorted({s['match_id'] for s in sources}):
        sample = [w for w in summaries if w['match_id'] == match_id and w['profile_sample']]
        counts = Counter(w['group'] for w in sample)
        matches.append({'id': match_id, 'name': match_id.removeprefix('match:'), 'sample_windows': len(sample),
                        'sample_seconds': round(sum(w['end']-w['start'] for w in sample), 3),
                        'groups': [{'group': g['id'], 'windows': counts[g['id']],
                                    'share': counts[g['id']]/len(sample) if sample else 0} for g in groups]})
    result = {'id': identity, 'created': time.time(), 'version': VERSION, 'feature_version': FEATURE_VERSION,
              'dataset_ids': dataset_ids, 'reference_ids': reference_ids, 'player': datasets[0]['player'],
              'windows': summaries, 'groups': groups, 'sources': sources, 'matches': matches,
              'model': {'feature_names': names, 'center': scaler.center_.tolist(), 'scale': scaler.scale_.tolist(),
                        'centers': model.cluster_centers_.tolist(), 'fit_windows': [key(w) for w in fitting],
                        'fit_sources': sorted({w['source_hash'] for w in fitting}), 'fit_mode': 'reference_only' if reference_ids else 'selected_library_exploration',
                        'k': chosen, 'initialization_ARI': stability, 'metrics': metrics,
                        'selection': 'User-selected k' if clusters else 'Highest silhouette among tested k; exploratory, not semantic validation'},
              'vectors': all_z.tolist(), 'values': all_x.tolist(), 'limitations': LIMITATIONS,
              'dataset_provenance': [{'id': d['id'], 'match': d['match'], 'archive_sha256': d['archive_sha256'], 'source_sha256': d['source']['sha256']} for d in datasets]}
    store.write('explorations', identity, result)
    progress('Movement library ready', 1)
    return {'exploration_id': identity}


def public_exploration(record):
    return {k: v for k, v in record.items() if k not in {'vectors', 'values'}}


def match_examples(record, match_id, curated=()):
    """Match-scoped group examples, with explicitly identified demo selections."""
    names = record['model']['feature_names']
    centers = np.array(record['model']['centers'])
    raw = centers*np.array(record['model']['scale'])+np.array(record['model']['center'])
    knees = [names.index(f) for f in ('left_knee_median', 'right_knee_median') if f in names]
    order = sorted(range(len(centers)), key=lambda i: float(raw[i, knees].mean()) if knees else i)
    vectors = np.array(record['vectors'])
    result = []
    for group in record['groups']:
        indices = [i for i,w in enumerate(record['windows']) if w['match_id']==match_id and w['group']==group['id']]
        ranked = sorted(indices,key=lambda i: (record['windows'][i]['key'] not in curated,
                                               curated.index(record['windows'][i]['key']) if record['windows'][i]['key'] in curated else float(np.linalg.norm(vectors[i]-centers[group['id']]))))
        examples, tracks = [], set()
        for i in ranked:
            w = record['windows'][i]; track=(w['source_hash'],w['tracklet_id'])
            if track in tracks:
                continue
            examples.append(w); tracks.add(track)
            if len(examples)==3:
                break
        title = ('More leg bend & variation' if group['id']==order[0] else 'Straighter-leg postures') if knees and len(order)==2 else group['name']
        result.append({'id':group['id'],'name':title,'count':len(indices),'examples':examples,
                       'curated':any(w['key'] in curated for w in examples)})
    return result


def find_index(record, window_key):
    try:
        return next(i for i, w in enumerate(record['windows']) if w['key'] == window_key)
    except StopIteration:
        raise ValueError('Choose a usable window from this frozen exploration') from None


def search(record, seed_key, radius=None, cross_match_only=False, same_match_only=False):
    if cross_match_only and same_match_only:
        raise ValueError('Choose this match or other matches, not both')
    seed_i = find_index(record, seed_key)
    seed = record['windows'][seed_i]
    z = np.array(record['vectors'])
    distances = np.linalg.norm(z-z[seed_i], axis=1)
    eligible = [i for i, w in enumerate(record['windows']) if i != seed_i and
                not (w['source_hash'] == seed['source_hash'] and w['start'] < seed['end']-1e-6 and w['end'] > seed['start']+1e-6) and
                (not cross_match_only or (w['match_id'] != seed['match_id'] and w['source_hash'] != seed['source_hash'])) and
                (not same_match_only or w['match_id'] == seed['match_id'])]
    eligible.sort(key=lambda i: (distances[i], record['windows'][i]['key']))
    # A suggested browsing radius, not a validated similarity decision threshold.
    suggested = float(distances[eligible[min(9, len(eligible)-1)]]) if eligible else 0.
    if radius is None:
        radius = suggested
    if not np.isfinite(radius) or not 0 <= radius <= 10000:
        raise ValueError('Choose a finite nonnegative similarity radius up to 10000')
    hits = [record['windows'][i] | {'distance': float(distances[i])} for i in eligible if distances[i] <= radius+1e-9]
    timelines = []
    for source in record['sources']:
        if same_match_only and source['match_id'] != seed['match_id']:
            continue
        part = [w for w in hits if w['source_hash'] == source['id']]
        intervals = interval_union([[w['start'], w['end']] for w in part])
        duration = seconds(intervals)
        timelines.append(source | {'matches': part, 'matching_intervals': intervals, 'matched_windows': len(part),
                                    'bouts': len(intervals), 'matching_seconds': duration,
                                    'share_of_usable_observed_time': duration/source['usable_seconds'] if source['usable_seconds'] else None})
    return {'exploration_id': record['id'], 'seed': seed, 'radius': float(radius), 'suggested_radius': suggested,
            'threshold_basis': 'Suggested radius includes up to ten nearest eligible examples; review clips to validate relevance.',
            'cross_match_only': cross_match_only, 'same_match_only': same_match_only, 'eligible_count': len(eligible), 'hits': hits, 'timelines': timelines,
            'matched_windows': len(hits), 'bouts': sum(t['bouts'] for t in timelines),
            'matching_seconds': round(sum(t['matching_seconds'] for t in timelines), 4),
            'excluded_seed_overlap': True, 'limitations': record['limitations']}


def compare_regions(record, seed_key, comparison_key):
    i, j = find_index(record, seed_key), find_index(record, comparison_key)
    z, values = np.array(record['vectors']), np.array(record['values'])
    squared = (z[i]-z[j])**2
    total = float(squared.sum())
    features = [{'feature': name, 'label': LABELS[name], 'region': region_for(name),
                 'query': float(values[i, n]), 'reference': float(values[j, n]),
                 'difference': float(values[i, n]-values[j, n]),
                 'squared_distance': float(squared[n]), 'share': float(squared[n]/total) if total > 1e-12 else 0.}
                for n, name in enumerate(record['model']['feature_names'])]
    return {'seed_key': seed_key, 'comparison_key': comparison_key, 'distance': float(np.sqrt(total)),
            'regions': [{'id': region, 'label': label, 'share': sum(f['share'] for f in features if f['region'] == region),
                         'features': sorted([f for f in features if f['region'] == region], key=lambda f: f['share'], reverse=True)}
                        for region, label in REGIONS.items()],
            'meaning': 'Share of squared standardized descriptor distance for this pair. This is not muscle activation, pain or injury risk.'}
