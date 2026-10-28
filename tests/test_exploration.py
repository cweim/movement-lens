import copy
import io
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import make_zip
from movement_lens.app import create_app
from movement_lens.exploration import create_exploration, search, compare_regions
from movement_lens.importer import import_dataset
from movement_lens.reviews import ReviewRequest, save_review, build_review_report
from movement_lens.store import sha_file


def catalogue(store, cohort):
    ref, query, _ = cohort
    xid = create_exploration(store, [ref, query], [ref], 2)['exploration_id']
    return store.read('explorations', xid)


def test_scaler_fits_only_reference_and_previous_records_stay_immutable(store, cohort):
    ref, query, _ = cohort
    old = {str(p):sha_file(p) for p in (store.root/'datasets').glob('*/record.json')}
    c = catalogue(store, cohort)
    assert c['model']['fit_mode'] == 'reference_only'
    assert all(k.startswith(ref+':') for k in c['model']['fit_windows'])
    rows = store.read('datasets', ref)['windows']
    names = c['model']['feature_names']
    expected = np.median([[w['features'][f] for f in names] for w in rows], axis=0)
    np.testing.assert_allclose(c['model']['center'], expected)
    assert all(sha_file(p) == digest for p, digest in [( __import__('pathlib').Path(p),v) for p,v in old.items()])
    assert create_exploration(store,[query,ref],[ref],2)['cached']


def test_zero_radius_and_cross_match_filter_and_no_self_match(store, cohort):
    c = catalogue(store, cohort)
    seed = c['windows'][0]
    result = search(c, seed['key'], 10000, True)
    assert result['hits'] and all(w['match_id'] != seed['match_id'] for w in result['hits'])
    assert seed['key'] not in {w['key'] for w in result['hits']}
    assert result['matching_seconds'] <= sum(s['usable_seconds'] for s in result['timelines'])
    zero = search(c, seed['key'], 0)
    assert all(w['distance'] <= 1e-9 for w in zero['hits'])
    with pytest.raises(ValueError,match='finite'):
        search(c,seed['key'],float('nan'))


def test_recurrence_merges_overlap_once_and_excludes_overlapping_seed_observations(store, cohort):
    c = copy.deepcopy(catalogue(store,cohort))
    # Controlled overlapping intervals in one source, with identical descriptor vectors.
    base = c['windows'][0]
    c['windows'] = [base | dict(key=f'k{i}',start=start,end=start+2,match_id='match:a') for i,start in enumerate([0.,1.,5.,6.])]
    c['vectors'] = [[0.,0.]]*4
    c['sources'] = [dict(id=base['source_hash'],match='a',match_id='match:a',duration=20.,usable_seconds=6.,usable_intervals=[[0.,3.],[5.,8.]],retained_intervals=[[0.,3.],[5.,8.]],window_count=4)]
    result = search(c,'k0',0)
    assert [w['key'] for w in result['hits']] == ['k2','k3']
    assert result['matched_windows'] == 2 and result['bouts'] == 1
    assert result['matching_seconds'] == 3.
    assert result['timelines'][0]['share_of_usable_observed_time'] == .5


def test_half_relative_timestamps_are_not_merged_across_sources(store,cohort):
    c = catalogue(store,cohort)
    result = search(c,c['windows'][0]['key'],10000)
    assert len({s['id'] for s in result['timelines']}) == 2
    assert result['matching_seconds'] == sum(s['matching_seconds'] for s in result['timelines'])


def test_other_matches_excludes_both_halves_and_same_source_with_inconsistent_label(store,cohort):
    c=copy.deepcopy(catalogue(store,cohort));base=c['windows'][0]
    c['windows']=[base|dict(key='seed',source_hash='a',match_id='match:game'),
                  base|dict(key='second-half',source_hash='b',match_id='match:game'),
                  base|dict(key='bad-label',source_hash='a',match_id='match:another-label',start=100.,end=102.),
                  base|dict(key='other-game',source_hash='c',match_id='match:other')]
    c['vectors']=[[0.,0.]]*4
    result=search(c,'seed',0,True)
    assert [w['key'] for w in result['hits']]==['other-game']


def test_duplicate_snapshots_do_not_multiply_observed_windows(store,cohort,tmp_path):
    ref, query, _ = cohort
    path = make_zip(tmp_path/'reference-again.zip',match='reference',count=24)
    with zipfile.ZipFile(path,'a') as archive:
        archive.comment=b're-exported snapshot'
    again = import_dataset(store,path,path.name)['dataset_id']
    c = store.read('explorations',create_exploration(store,[ref,again,query],[again],2)['exploration_id'])
    assert len(c['windows']) == 36 and len(c['model']['fit_windows']) == 24
    assert len({(w['source_hash'],w['start'],w['end']) for w in c['windows']}) == 36
    assert all(w['dataset_id'] == again for w in c['windows'] if w['match_id']=='match:reference')


def test_regional_contributions_sum_to_distance_and_handle_identical_vectors(store,cohort):
    c = catalogue(store,cohort);a,b = c['windows'][:2]
    pair = compare_regions(c,a['key'],b['key'])
    assert sum(r['share'] for r in pair['regions']) == pytest.approx(1.)
    assert sum(f['squared_distance'] if 'squared_distance' in f else 0 for r in pair['regions'] for f in r['features']) == pytest.approx(pair['distance']**2)
    same = compare_regions(c,a['key'],a['key'])
    assert same['distance'] == 0 and all(r['share'] == 0 for r in same['regions'])


def test_review_snapshot_restores_context_and_report_is_portable_and_escaped(store,cohort):
    c = catalogue(store,cohort);seed=c['windows'][0]['key'];hit=search(c,seed,10000)['hits'][0]
    body = ReviewRequest(seed_key=seed,radius=10000,selected_keys=[hit['key']],comparison_key=hit['key'],context={
        'reviewer':'Test physio','status':'staff_reviewed','symptoms':[{'region':'left_knee','severity':3,'reported_at':'2026-10-27'}],
        'staff_notes':'<script>alert(1)</script>', 'decision':'Staff-authored review', 'follow_up':'Reassess with team protocol'})
    vid=save_review(store,c,body)['review_id']
    frozen=store.read('reviews',vid)
    assert frozen['facts']['context']['symptoms'][0]['severity'] == 3
    rid=build_review_report(store,vid)['report_id']
    with zipfile.ZipFile(store.path('reports',rid)/'report.zip') as z:
        assert {'report.html','report.json','provenance.json','matching-windows.csv','recurrence.csv','match-profiles.csv','body-regions.csv'} <= set(z.namelist())
        doc=z.read('report.html').decode()
        assert '<script>alert' not in doc and '&lt;script&gt;' in doc
        assert 'Staff-authored review' in doc and 'source time' in doc
        assert json.loads(z.read('report.json'))['facts']['context']['status']=='staff_reviewed'
    assert store.read('reviews',vid)==frozen


def test_review_rejects_foreign_curated_clip_and_unsigned_review(store,cohort):
    c=catalogue(store,cohort);seed=c['windows'][0]['key']
    with pytest.raises(ValueError,match='Curated'):
        save_review(store,c,ReviewRequest(seed_key=seed,radius=0,selected_keys=['foreign']))
    with pytest.raises(ValueError,match='reviewer'):
        save_review(store,c,ReviewRequest(seed_key=seed,radius=10000,context={'status':'staff_reviewed'}))


def test_end_to_end_api_catalogue_search_regions_review_and_download(store,cohort):
    ref,query,_=cohort;client=TestClient(create_app(store.root))
    response=client.post('/api/explorations',json={'dataset_ids':[ref,query],'reference_ids':[ref],'clusters':2})
    job=client.get('/api/jobs/'+response.json()['job_id']).json();assert job['status']=='done'
    xid=job['result']['exploration_id'];c=client.get('/api/explorations/'+xid).json()
    assert 'vectors' not in c and c['model']['fit_mode']=='reference_only'
    seed=c['windows'][0]['key'];r=client.post(f'/api/explorations/{xid}/search',json={'seed_key':seed,'radius':10000}).json()
    hit=r['hits'][0]['key'];body={'seed_key':seed,'radius':10000,'comparison_key':hit,'selected_keys':[hit]}
    assert client.post(f'/api/explorations/{xid}/regions',json={'seed_key':seed,'comparison_key':hit}).status_code==200
    local=client.post(f'/api/explorations/{xid}/explain',json=body).json();assert local['provider']=='local' and local['observations']
    vid=client.post(f'/api/explorations/{xid}/reviews',json=body).json()['review_id']
    response=client.post(f'/api/reviews/{vid}/reports',json={'include_media':False})
    job=client.get('/api/jobs/'+response.json()['job_id']).json();assert job['status']=='done'
    download=client.get('/api/reports/'+job['result']['report_id']+'/download')
    assert download.status_code==200 and zipfile.is_zipfile(io.BytesIO(download.content))
