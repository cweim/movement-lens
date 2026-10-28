import io
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import arrays, make_zip
from movement_lens.analysis import analyse, evidence, explain
from movement_lens.app import create_app
from movement_lens.features import FEATURES, describe, interval_union
from movement_lens.importer import import_dataset, load_arrays
from movement_lens.reports import build_report


def test_geometry_is_translation_scale_invariant_but_masks_survive():
    a=arrays();row={'start':0,'end':2,'pose_provenance':'source_bound'}
    one=describe(a,row)
    assert one['quality']['usable'] and len(one['features'])==16
    b={k:v.copy() for k,v in a.items()};b['keypoints']=b['keypoints']*2+[100,50]
    two=describe(b,row)
    np.testing.assert_allclose(list(one['features'].values()),list(two['features'].values()),atol=1e-4)
    b['valid_mask'][:20,15]=False
    assert not describe(b,row)['quality']['usable']
    assert describe(b,row)['traces']['left_knee'][:20]==[None]*20


def test_unverified_sources_and_source_gaps_withheld():
    a=arrays();row={'start':0,'end':2,'pose_provenance':'imported_research_cache_unverified_source_binding'}
    assert not describe(a,row)['quality']['usable']
    a['source_times']=np.array([0,.08,.16,1.,1.92])
    q=describe(a,row)['quality']
    assert any('gap' in s for s in q['reasons'])


def test_identity_ambiguity_review_is_not_overridden_by_good_pose():
    a=arrays();row={'start':0,'end':2,'pose_provenance':'source_bound','flags':['identity_ambiguous']}
    result=describe(a,row)
    assert not result['quality']['usable']
    assert 'Withheld by source review: identity ambiguous' in result['quality']['reasons']


def test_coverage_merges_overlapping_intervals():
    assert interval_union([[1,3],[2,4],[7,9],[4,5]])==[[1.,5.],[7.,9.]]


def test_import_ids_and_optional_media(store,tmp_path):
    p=make_zip(tmp_path/'one.zip',count=3,media=True)
    result=import_dataset(store,p,'one.zip');d=store.read('datasets',result['dataset_id'])
    assert len(d['windows'])==3 and d['usable_count']==3 and d['media_count']==3
    assert d['coverage']['observed_seconds']==6 and d['coverage']['fraction'] is None
    assert d['windows'][0]['original_id']=='reference-window-0'
    assert d['windows'][0]['id']=='w_00000'
    assert 'filename' not in d['source']


def test_reimport_deduplicates_exact_export(store,tmp_path):
    p=make_zip(tmp_path/'a.zip',count=2);data=p.read_bytes()
    a=import_dataset(store,p,'a.zip')
    other=tmp_path/'b.zip';other.write_bytes(data)
    b=import_dataset(store,other,'b.zip')
    assert a['dataset_id']==b['dataset_id'] and b['already_imported']
    assert len(store.list('datasets'))==1


@pytest.mark.parametrize('mutation',[
    lambda a,i:a.update(times=np.linspace(i*3,i*3+2,50)),
    lambda a,i:a.update(valid_mask=np.ones((49,17))),
    lambda a,i:a.update(kp_conf=np.full((50,17),np.nan)),
    lambda a,i:a.update(source_frame_indices=a['source_frame_indices']+2),
    lambda a,i:a.update(keypoints=np.zeros((50,17,2),dtype=object)),
])
def test_invalid_arrays_are_atomic(store,tmp_path,mutation):
    p=make_zip(tmp_path/'bad.zip',count=2,mutate=mutation)
    with pytest.raises(ValueError):import_dataset(store,p,'bad.zip')
    assert store.list('datasets')==[]
    assert list((store.root/'uploads').iterdir())==[]


def test_zip_traversal_rejected(store,tmp_path):
    p=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../outside','bad')
    with pytest.raises(ValueError,match='unsafe'):import_dataset(store,p,'unsafe.zip')
    assert not (store.root/'outside').exists()


def test_forged_giant_numpy_header_rejected_before_allocation():
    header=io.BytesIO()
    np.lib.format.write_array_header_1_0(header,{'descr':'<f8','fortran_order':False,'shape':(10**12,)})
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w') as z:z.writestr('times.npy',header.getvalue())
    with pytest.raises(ValueError,match='oversized'):load_arrays(payload.getvalue(),{'start':0,'end':2})


def test_reference_only_scaling_and_distinct_examples(store,cohort):
    ref,query,cal=cohort
    identity=analyse(store,query,[ref],cal)['analysis_id'];a=store.read('analyses',identity)
    assert a['calibration']['available'] and a['query_count']==12
    ref_data=store.read('datasets',ref)
    names=a['feature_names'];X=np.array([[w['features'][f] for f in names] for w in ref_data['windows']])
    np.testing.assert_allclose(a['model']['scaler_center'],np.median(X,axis=0))
    assert all(e['comparisons'] for e in a['episodes'])
    b=evidence(store,identity,a['episodes'][0]['id'])
    assert len({c['window']['tracklet_id'] for c in b['comparisons']})==3
    assert b['query']['window']['original_id'].startswith('query-window-')
    assert 'does not establish' in explain(b,question='Does this predict injury risk?')['summary']


def test_same_match_and_player_split_enforced(store,cohort):
    ref,query,cal=cohort
    with pytest.raises(ValueError,match='separate'):analyse(store,query,[query])
    d=store.read('datasets',cal);d['match']=store.read('datasets',ref)['match'];store.write('datasets',cal,d)
    with pytest.raises(ValueError,match='different match'):analyse(store,query,[ref],cal)
    d['match']='another';d['player']='another player';store.write('datasets',cal,d)
    with pytest.raises(ValueError,match='same player'):analyse(store,query,[ref],cal)


@pytest.mark.parametrize('role', ['query', 'calibration'])
@pytest.mark.parametrize('reference_name', ['Fixture', 'Fixture · first source half'])
def test_opposite_source_halves_cannot_cross_match_splits(store,cohort,role,reference_name):
    ref,query,cal=cohort
    d=store.read('datasets',ref);d['match']=reference_name;store.write('datasets',ref,d)
    other=query if role=='query' else cal
    d=store.read('datasets',other);d['match']='Fixture · second source half';store.write('datasets',other,d)
    with pytest.raises(ValueError,match='match/source'):
        analyse(store,query,[ref],cal if role=='calibration' else None)


def test_calibration_is_optional_and_cache_immutable(store,cohort):
    ref,query,_=cohort
    r=analyse(store,query,[ref]);a=store.read('analyses',r['analysis_id'])
    assert not a['calibration']['available']
    assert all(e['percentile'] is None for e in a['episodes'])
    assert analyse(store,query,[ref])['cached']


def test_report_is_portable_and_escaped(store,cohort):
    ref,query,_=cohort
    aid=analyse(store,query,[ref])['analysis_id'];e=store.read('analyses',aid)['episodes'][0]
    r=build_report(store,aid,[e['id']],{e['id']:'<script>alert(1)</script>'})
    with zipfile.ZipFile(store.path('reports',r['report_id'])/'report.zip') as z:
        assert {'report.html','report.json','provenance.json','episodes.csv','comparisons.csv'}<=set(z.namelist())
        text=z.read('report.html').decode()
        assert '<script>' not in text and '&lt;script&gt;' in text
        assert 'blob:' not in text and '/Users/' not in text
        record=json.loads(z.read('report.json'));assert record['items'][0]['note_author']=='user'
        assert record['items'][0]['query']['window']['original_id'].startswith('query-window-')


def test_api_import_media_range_error_and_origin(tmp_path):
    client=TestClient(create_app(tmp_path/'api-state'))
    p=make_zip(tmp_path/'input.zip',count=3,media=True)
    with p.open('rb') as f:r=client.post('/api/datasets',files={'file':('dataset.zip',f,'application/zip')})
    j=client.get('/api/jobs/'+r.json()['job_id']).json();assert j['status']=='done'
    did=j['result']['dataset_id'];d=client.get('/api/datasets/'+did).json();w=d['windows'][0]
    actual=client.get(f'/api/datasets/{did}/windows/{w["id"]}').json()
    assert len(actual['skeleton'])==50
    media=client.get(actual['video_url'],headers={'Range':'bytes=0-3'})
    assert media.status_code==206 and media.content==b'test'
    assert client.get('/api/datasets/not_found').status_code==404
    assert client.get('/api/status',headers={'Origin':'https://unrelated.example'}).status_code==403


def test_api_analysis_explanation_report_roundtrip(tmp_path):
    client=TestClient(create_app(tmp_path/'api-state'));ids=[]
    for name in ['ref','query']:
        p=make_zip(tmp_path/f'{name}.zip',name,count=12)
        with p.open('rb') as f:r=client.post('/api/datasets',files={'file':(p.name,f)})
        ids.append(client.get('/api/jobs/'+r.json()['job_id']).json()['result']['dataset_id'])
    j=client.post('/api/analyses',json={'query_id':ids[1],'reference_ids':[ids[0]]}).json()['job_id']
    result=client.get('/api/jobs/'+j).json();assert result['status']=='done'
    aid=result['result']['analysis_id'];a=client.get('/api/analyses/'+aid).json();eid=a['episodes'][0]['id']
    x=client.post(f'/api/analyses/{aid}/episodes/{eid}/explain',json={'audience':'viewer'}).json();assert x['provider']=='local' and x['observations']
    j=client.post(f'/api/analyses/{aid}/reports',json={'episode_ids':[eid]}).json()['job_id']
    rid=client.get('/api/jobs/'+j).json()['result']['report_id']
    assert client.get(f'/api/reports/{rid}/download').status_code==200
