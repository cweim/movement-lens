import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from movement_lens import cloud
from movement_lens.analysis import analyse, evidence
from movement_lens.reports import build_report


class Context:
    def __enter__(self):return self
    def __exit__(self,*_):return False


def test_private_azure_roundtrip_checks_download_hash(monkeypatch,store,cohort):
    import azure.identity
    import azure.storage.blob
    monkeypatch.setenv('MOVEMENT_LENS_AZURE_ACCOUNT_URL','https://exampleaccount.blob.core.windows.net')
    monkeypatch.setenv('MOVEMENT_LENS_AZURE_CONTAINER','private-reports')
    monkeypatch.setattr(azure.identity,'DefaultAzureCredential',lambda **kw:Context())
    data={};state={'public':False,'uploads':0}
    class Blob:
        def __init__(self,name):self.name=name
        def exists(self):return self.name in data
        def upload_blob(self,f,overwrite,metadata,content_settings):
            assert not overwrite;data[self.name]={'bytes':f.read(),'metadata':metadata};state['uploads']+=1
        def get_blob_properties(self):return SimpleNamespace(metadata=data[self.name]['metadata'])
        def download_blob(self):return SimpleNamespace(readall=lambda:data[self.name]['bytes'])
    class Container(Context):
        def get_container_properties(self):return {'public_access':'blob' if state['public'] else None}
        def get_blob_client(self,name):return Blob(name)
    monkeypatch.setattr(azure.storage.blob,'ContainerClient',lambda *a,**kw:Container())
    ref,query,_=cohort;aid=analyse(store,query,[ref])['analysis_id'];eid=store.read('analyses',aid)['episodes'][0]['id']
    rid=build_report(store,aid,[eid])['report_id']
    cloud.save_report(store,rid);cloud.save_report(store,rid)
    assert state['uploads']==1
    assert cloud.download_report(store,rid)==(store.path('reports',rid)/'report.zip').read_bytes()
    name=next(iter(data));original=data[name]['bytes'];data[name]['bytes']=b'changed'
    with pytest.raises(ValueError,match='checksum'):cloud.download_report(store,rid)
    data[name]['bytes']=original;state['public']=True
    with pytest.raises(ValueError,match='private'):cloud.save_report(store,rid)
    with pytest.raises(ValueError,match='private'):cloud.download_report(store,rid)


def install_fake_foundry(monkeypatch,responses,requests=None):
    import azure.identity
    monkeypatch.setattr(cloud,'config',lambda:{'foundry':{'available':True}})
    monkeypatch.setenv('MOVEMENT_LENS_FOUNDRY_PROJECT_ENDPOINT','https://example.services.ai.azure.com/api/projects/demo')
    monkeypatch.setenv('MOVEMENT_LENS_FOUNDRY_MODEL','test-deployment')
    monkeypatch.setattr(azure.identity,'DefaultAzureCredential',lambda **kw:Context())
    inputs=[]
    class Client(Context):
        def __init__(self):self.responses=self
        def with_options(self,**kwargs):
            assert kwargs=={'timeout':45,'max_retries':1}
            return self
        def create(self,**kwargs):
            assert kwargs['store'] is False
            assert kwargs['max_output_tokens'] == 4096
            if requests is not None:
                requests.append(kwargs.copy())
            inputs.append(list(kwargs['input']))
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
    class Project(Context):
        def __init__(self,**kwargs):pass
        def get_openai_client(self):return Client()
    module=ModuleType('azure.ai.projects');module.AIProjectClient=Project
    monkeypatch.setitem(sys.modules,'azure.ai.projects',module)
    return inputs


def test_foundry_executes_readonly_tools_and_cites_actual_evidence(monkeypatch,store,cohort):
    ref,query,_=cohort;aid=analyse(store,query,[ref])['analysis_id'];eid=store.read('analyses',aid)['episodes'][0]['id'];bundle=evidence(store,aid,eid)
    wid=bundle['query']['window']['original_id']
    call=SimpleNamespace(type='function_call',name='get_episode',arguments='{}',call_id='call_a')
    responses=[SimpleNamespace(output=[call]),SimpleNamespace(output=[],output_text=json.dumps({'summary':'The query differs from its references.',
        'observations':[{'text':'Inspect the projected movement in the available clip.','evidence_ids':[wid]}],'limitations':['Coverage is incomplete.']}))]
    inputs=install_fake_foundry(monkeypatch,responses)
    result=cloud.foundry_explain(bundle,'analyst','Explain this episode')
    assert result['provider']=='foundry' and result['tool_trace']==['get_episode']
    output=next(x for x in inputs[1] if isinstance(x,dict) and x.get('type')=='function_call_output')
    assert json.loads(output['output'])['query_window_id']==wid


@pytest.mark.parametrize('bad', ['invented-citation','numeric-prose','no-tools'])
def test_foundry_rejects_unsupported_outputs(monkeypatch,store,cohort,bad):
    ref,query,_=cohort;aid=analyse(store,query,[ref])['analysis_id'];eid=store.read('analyses',aid)['episodes'][0]['id'];b=evidence(store,aid,eid)
    wid=b['query']['window']['original_id']
    final=SimpleNamespace(output=[],output_text=json.dumps({'summary':'Score 999' if bad=='numeric-prose' else 'Inspect the movement.',
          'observations':[{'text':'A movement difference.','evidence_ids':['fake-id' if bad=='invented-citation' else wid]}],'limitations':[]}))
    calls=[] if bad=='no-tools' else [SimpleNamespace(output=[SimpleNamespace(type='function_call',name='get_comparisons',arguments='{}',call_id='a')])]
    install_fake_foundry(monkeypatch,calls+[final])
    with pytest.raises(ValueError):cloud.foundry_explain(b,'viewer','Explain')
