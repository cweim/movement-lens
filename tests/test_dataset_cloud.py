import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from conftest import make_zip
from test_cloud import Context, install_fake_foundry
from movement_lens import azure_datasets, cloud
from movement_lens.exploration import create_exploration, search
from movement_lens.reviews import ReviewRequest, review_facts


def install_storage(monkeypatch, payload):
    import azure.identity
    import azure.storage.blob
    sha=hashlib.sha256(payload).hexdigest();name=f'touchline/test_job/{sha}/dataset.zip'
    state={'public':False,'bytes':payload,'sha':sha,'size':len(payload),'etag':'"one"','calls':[]}
    monkeypatch.setenv('MOVEMENT_LENS_AZURE_SOURCE_ACCOUNT_URL','https://exampleaccount.blob.core.windows.net')
    monkeypatch.setenv('MOVEMENT_LENS_AZURE_SOURCE_CONTAINER','private-datasets')
    monkeypatch.setattr(azure.identity,'DefaultAzureCredential',lambda **_:Context())
    class Pages:
        continuation_token='next-page'
        def __init__(self):self.done=False
        def __iter__(self):return self
        def __next__(self):
            if self.done:raise StopIteration
            self.done=True
            return iter([SimpleNamespace(name=name,size=state['size'],metadata={'sha256':state['sha']},etag=state['etag'],last_modified=datetime.now(timezone.utc)),
                         SimpleNamespace(name='unrelated/report.zip',size=12,metadata={},etag='x',last_modified=None)])
    class Blob:
        def get_blob_properties(self):return SimpleNamespace(size=state['size'],metadata={'sha256':state['sha']},etag=state['etag'])
        def download_blob(self,**kwargs):
            state['calls'].append(kwargs)
            return SimpleNamespace(chunks=lambda:iter([state['bytes'][:100],state['bytes'][100:]]))
    class Container(Context):
        def get_container_properties(self):return {'public_access':'blob' if state['public'] else None}
        def get_blob_client(self,chosen):assert chosen==name;return Blob()
        def list_blobs(self,**kwargs):
            assert kwargs['name_starts_with']=='touchline/' and kwargs['results_per_page']==100
            return SimpleNamespace(by_page=lambda **_:Pages())
    monkeypatch.setattr(azure.storage.blob,'ContainerClient',lambda *a,**kw:Container())
    return state,name,sha


def test_private_listing_and_verified_download_use_normal_quality_importer(monkeypatch,store,tmp_path):
    path=make_zip(tmp_path/'dataset.zip',count=4,provenance='unverified')
    state,name,sha=install_storage(monkeypatch,path.read_bytes())
    listing=azure_datasets.list_datasets()
    assert len(listing['items'])==1 and listing['cursor']=='next-page'
    result=azure_datasets.import_snapshot(store,name,sha,state['etag'])
    ds=store.read('datasets',result['dataset_id'])
    assert ds['archive_sha256']==sha and ds['window_count']==4 and ds['usable_count']==0
    assert result['verified_sha256']==sha and state['calls'][0]['etag']=='"one"'
    assert not list((store.root/'uploads').glob('*.zip'))


@pytest.mark.parametrize('failure',['public','checksum','etag','oversize','metadata'])
def test_cloud_dataset_rejects_changed_unsafe_or_oversized_snapshot(monkeypatch,store,tmp_path,failure):
    path=make_zip(tmp_path/'dataset.zip',count=4)
    state,name,sha=install_storage(monkeypatch,path.read_bytes())
    if failure=='public':state['public']=True
    if failure=='checksum':state['bytes']=state['bytes'][:-1]+b'x'
    if failure=='etag':state['etag']='"two"'
    if failure=='oversize':state['size']=2*1024**3
    if failure=='metadata':state['sha']='0'*64
    with pytest.raises(ValueError):azure_datasets.import_snapshot(store,name,sha,'"one"')
    assert not store.list('datasets') and not list((store.root/'uploads').glob('*.zip'))


def test_source_uses_touchline_configuration_and_validates_blob_path(monkeypatch,store):
    for name in ['MOVEMENT_LENS_AZURE_SOURCE_ACCOUNT_URL','MOVEMENT_LENS_AZURE_SOURCE_CONTAINER','MOVEMENT_LENS_AZURE_ACCOUNT_URL','MOVEMENT_LENS_AZURE_CONTAINER']:
        monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('TOUCHLINE_AZURE_ACCOUNT_URL','https://touchlinesource.blob.core.windows.net')
    monkeypatch.setenv('TOUCHLINE_AZURE_CONTAINER','touchline-datasets')
    assert azure_datasets.configuration()['configured']
    with pytest.raises(ValueError,match='immutable'):
        azure_datasets.import_snapshot(store,'../../secret','0'*64)


def pattern_facts(store,cohort):
    ref,query,_=cohort;xid=create_exploration(store,[ref,query],[ref],2)['exploration_id'];c=store.read('explorations',xid)
    seed=c['windows'][0]['key'];hit=search(c,seed,10000)['hits'][0]['key']
    return review_facts(c,ReviewRequest(seed_key=seed,radius=10000,comparison_key=hit))


def test_pattern_foundry_retrieves_actual_research_and_window_evidence(monkeypatch,store,cohort):
    facts=pattern_facts(store,cohort);seed=facts['search']['seed']['key']
    calls=[SimpleNamespace(type='function_call',name=name,arguments='{}',call_id=name) for name in
           ['get_pattern_timeline','get_region_evidence','get_recovery_context','retrieve_research']]
    final={'summary':'Inspect the observed 2D pattern and its coverage.',
           'observations':[{'text':'The clips provide projected movement evidence.', 'evidence_ids':[seed]},
                           {'text':'Research context does not establish individual recovery needs.', 'evidence_ids':['paper:opencap2023']}],
           'limitations':['Staff assessment and follow-up outcomes remain necessary.']}
    requests=[]
    inputs=install_fake_foundry(monkeypatch,[SimpleNamespace(output=calls),SimpleNamespace(output=[],output_text=__import__('json').dumps(final))],requests=requests)
    response=cloud.foundry_pattern_explain(facts,'Explain this recurring movement')
    assert response['provider']=='foundry' and 'retrieve_research' in response['tool_trace']
    assert any(isinstance(item,dict) and item.get('type')=='function_call_output' for item in inputs[1])
    assert requests[0]['tool_choice']=='required'
    format=requests[1]['text']['format']
    choices=format['schema']['properties']['observations']['items']['properties']['evidence_ids']['items']['enum']
    assert format['strict'] is True and requests[1]['parallel_tool_calls'] is False
    assert set(choices)==set(response['evidence_ids'])
    assert 'profile:'+facts['profiles'][0]['id'] not in choices  # Match profiles were not retrieved.


def test_pattern_foundry_requires_missing_context_before_final_draft(monkeypatch,store,cohort):
    facts=pattern_facts(store,cohort);seed=facts['search']['seed']['key']
    calls=[SimpleNamespace(output=[SimpleNamespace(type='function_call',name=name,arguments='{}',call_id=name)])
           for name in ['get_pattern_timeline','get_recovery_context']]
    final={'summary':'Observed projected movement.', 'observations':[
        {'text':'Review the available movement.', 'evidence_ids':[seed]},
        {'text':'No staff symptoms were supplied.', 'evidence_ids':['staff_context']}], 'limitations':[]}
    requests=[]
    install_fake_foundry(monkeypatch,calls+[SimpleNamespace(output=[],output_text=__import__('json').dumps(final))],requests=requests)
    result=cloud.foundry_pattern_explain(facts,'Explain')
    assert requests[1]['tool_choice']=={'type':'function','name':'get_recovery_context'}
    allowed=requests[1]['text']['format']['schema']['properties']['observations']['items']['properties']['evidence_ids']['items']['enum']
    assert 'staff_context' not in allowed
    assert result['tool_trace']==['get_pattern_timeline','get_recovery_context']


def test_pattern_foundry_rate_limit_has_actionable_message(monkeypatch,store,cohort):
    class Limited(Exception):
        status_code = 429
    install_fake_foundry(monkeypatch,[Limited('Private SDK details must not be exposed')])
    with pytest.raises(ValueError, match='Foundry rate limit reached') as error:
        cloud.foundry_pattern_explain(pattern_facts(store,cohort),'Explain')
    assert 'Private SDK' not in str(error.value)


@pytest.mark.parametrize('failure',['unretrieved_paper','numeric_claim','treatment'])
def test_pattern_foundry_rejects_unsupported_claims_or_unretrieved_citations(monkeypatch,store,cohort,failure):
    facts=pattern_facts(store,cohort);seed=facts['search']['seed']['key']
    text={'unretrieved_paper':'Research says inspect movement.','numeric_claim':'There are 99 repetitions.','treatment':'The player needs treatment.'}[failure]
    final={'summary':'Movement review.', 'observations':[{'text':text,'evidence_ids':['paper:opencap2023' if failure=='unretrieved_paper' else seed]}], 'limitations':[]}
    calls=[SimpleNamespace(type='function_call',name=name,arguments='{}',call_id=name) for name in ['get_pattern_timeline','get_recovery_context']]
    install_fake_foundry(monkeypatch,[SimpleNamespace(output=calls),SimpleNamespace(output=[],output_text=__import__('json').dumps(final))])
    with pytest.raises(ValueError):cloud.foundry_pattern_explain(facts,'Explain')
