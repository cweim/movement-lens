import copy
import base64
import json
import sys
import zipfile
from types import ModuleType,SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import make_zip
from test_cloud import Context
from movement_lens import clusters,cluster_ai
from movement_lens.app import create_app
from movement_lens.importer import import_dataset
from movement_lens.cluster_research import STUDIES


@pytest.fixture
def match_workspace(store,tmp_path):
    halves=[]
    for half,word,offset in [(1,'first',0),(2,'second',12)]:
        p=make_zip(tmp_path/f'half{half}.zip',match=f'game · {word} source half',count=16,offset=offset)
        did=import_dataset(store,p,p.name)['dataset_id'];d=store.read('datasets',did)
        halves.append({'half':half,'dataset_id':did,'source_hash':d['source']['sha256'],'usable_windows':d['usable_count'],'raw_windows':16,'independent_candidates':16,'imported_windows':16})
    p=make_zip(tmp_path/'unrelated.zip',match='another match',count=24)
    other=import_dataset(store,p,p.name)['dataset_id']
    directory=store.root/'prepared';directory.mkdir()
    (directory/'cluster-match-audit.json').write_text(json.dumps({'dataset_ids':[h['dataset_id'] for h in halves],'halves':halves,'sampling':'All independent candidates.'}))
    result=clusters.build_workspace(store);work=store.read('cluster_workspaces',result['workspace_id'])
    return work,other


def test_single_match_auto_k_complete_aggregates_and_nonoverlapping_timeline(store,match_workspace):
    work,other=match_workspace
    assert work['model']['fit_mode']=='selected_library_exploration'
    assert not any(w['dataset_id']==other for w in work['windows'])
    assert work['model']['k']==max(work['model']['metrics'],key=lambda m:m['silhouette'])['k']
    assert all(0<=m['initialization_ARI']<=1 for m in work['model']['metrics'])
    assert work['independent_windows']==32 and work['observed_seconds']==64
    assert sum(b['observed_seconds'] for b in work['bins'])==64
    assert sum(g['observed_seconds'] for g in work['clusters'])==64
    assert sum(g['share_of_observed'] for g in work['clusters'])==pytest.approx(1)
    assert {s['half'] for s in work['sources']}=={1,2}
    for g in work['clusters']:
        members=[w for w in work['windows'] if w['group']==g['id']]
        assert len(members)==g['window_count']
        f=g['features'][0];values=[]
        for w in members:
            d=store.read('datasets',w['dataset_id']);original=next(x for x in d['windows'] if x['id']==w['id']);values.append(original['features'][f['feature']])
        assert f['median']==pytest.approx(np.median(values))
        reps=[next(w for w in members if w['key']==key) for key in g['representatives']]
        assert len({(w['source_hash'],w['tracklet_id']) for w in reps})==len(reps)
        assert g['boundary'] not in g['representatives']


def valid_draft(facts):
    cid=facts['cluster_evidence_id']
    return {'summary':'A recurring projected posture pattern with variation.',
            'observed':[{'text':'The examples illustrate the aggregate projected pattern.','evidence_ids':[cid]}],
            'physical_demands':[{'text':'General activity relevance depends on the reviewed category.','evidence_ids':[cid,'paper:nedelec2014']}],
            'recovery_context':[{'text':'Post-match recovery findings differ by intervention, population and outcome.','evidence_ids':['paper:ascensao2011','paper:kinugasa2009']}],
            'limitations':['Source gaps and camera viewpoint limit interpretation.']}


def test_category_gate_and_mixed_demand_is_withheld(match_workspace):
    work,_=match_workspace
    with pytest.raises(ValueError,match='confirm'):
        clusters.cluster_evidence(work,clusters.ClusterSelection(cluster_id=0))
    facts=clusters.cluster_evidence(work,clusters.ClusterSelection(cluster_id=0,category_id='mixed',reviewed=True))
    ids={facts['cluster_evidence_id'],*[p['id'] for p in STUDIES]}
    result=cluster_ai.validate_draft(valid_draft(facts),ids,facts)
    assert 'cannot confidently' in result['physical_demands'][0]['text']


@pytest.mark.parametrize('fault',['unretrieved','no_research','personal_advice'])
def test_unsupported_ai_outputs_are_rejected(match_workspace,fault):
    work,_=match_workspace;facts=clusters.cluster_evidence(work,clusters.ClusterSelection(cluster_id=0,category_id='running',reviewed=True));draft=valid_draft(facts)
    ids={facts['cluster_evidence_id'],*[p['id'] for p in STUDIES]}
    if fault=='unretrieved':draft['observed'][0]['evidence_ids']=['made-up']
    if fault=='no_research':draft['recovery_context'][0]['evidence_ids']=[facts['cluster_evidence_id']]
    if fault=='personal_advice':draft['recovery_context'][0]['text']='The player needs rest.'
    with pytest.raises(ValueError):cluster_ai.validate_draft(draft,ids,facts)


def test_ai_retrieves_whole_cluster_and_research_and_constrains_citations(monkeypatch,match_workspace,tmp_path):
    work,_=match_workspace;facts=clusters.cluster_evidence(work,clusters.ClusterSelection(cluster_id=0,reviewed=True,category_id='running'))
    calls=[SimpleNamespace(type='function_call',name=name,arguments='{}',call_id=name) for name in ['get_cluster_aggregate','get_cluster_examples','get_cluster_timeline','retrieve_recovery_research']]
    responses=[SimpleNamespace(output=calls),SimpleNamespace(output=[],output_text=json.dumps(valid_draft(facts)))];requests=[]
    monkeypatch.setattr(cluster_ai,'config',lambda:{'foundry':{'available':True}})
    monkeypatch.setenv('MOVEMENT_LENS_FOUNDRY_MODEL','unit-model');monkeypatch.setenv('MOVEMENT_LENS_FOUNDRY_PROJECT_ENDPOINT','https://unit.services.ai.azure.com/api/projects/test')
    import azure.identity
    monkeypatch.setattr(azure.identity,'DefaultAzureCredential',lambda **_:Context())
    class Client(Context):
        def __init__(self):self.responses=self
        def with_options(self,**kwargs):assert kwargs=={'timeout':60,'max_retries':1};return self
        def create(self,**kwargs):requests.append(copy.deepcopy(kwargs));return responses.pop(0)
    class Project(Context):
        def __init__(self,**kwargs):pass
        def get_openai_client(self):return Client()
    module=ModuleType('azure.ai.projects');module.AIProjectClient=Project;monkeypatch.setitem(sys.modules,'azure.ai.projects',module)
    strip=tmp_path/'sample.jpg';strip.write_bytes(b'unit-test-image')
    result=cluster_ai.explain_cluster(facts,[{'path':str(strip),'window_key':facts['examples'][0]['key']}])
    assert set(result['tool_trace'])=={c.name for c in calls}
    image=next(x for x in requests[0]['input'][0]['content'] if x['type']=='input_image')
    assert image['image_url']=='data:image/jpeg;base64,'+base64.b64encode(strip.read_bytes()).decode()
    assert image['detail']=='low' and result['images_sent']==1
    output=next(x for x in requests[1]['input'] if isinstance(x,dict) and x.get('type')=='function_call_output' and x['call_id']=='get_cluster_aggregate')
    assert json.loads(output['output'])['cluster']['window_count']==facts['group']['window_count']
    schema=requests[1]['text']['format']['schema'];choices=schema['properties']['observed']['items']['properties']['evidence_ids']['items']['enum']
    assert set(choices)==set(result['evidence_ids']) and requests[1]['store'] is False


def test_frozen_cluster_explanation_export_and_stale_binding(monkeypatch,store,match_workspace):
    work,_=match_workspace;body=clusters.ClusterSelection(cluster_id=0,category_id='descriptive',reviewed=True)
    facts=clusters.cluster_evidence(work,body);draft=clusters.local_cluster_brief(facts)
    result=clusters.save_cluster_explanation(store,work,clusters.ClusterExplainRequest(**body.model_dump(),provider='local'),draft,[])
    body.explanation_id=result['explanation_id']
    rid=clusters.export_cluster(store,work,body)['report_id']
    with zipfile.ZipFile(store.path('reports',rid)/'report.zip') as z:
        frozen=json.loads(z.read('report.json'));assert len(frozen['members'])==facts['group']['window_count']
        assert frozen['explanation']==draft
        assert {'cluster-members.csv','aggregate-features.csv','k-diagnostics.csv','timeline.json','candidate-audit.json'}<=set(z.namelist())
        assert 'General recovery context' in z.read('report.html').decode()
    altered=body.model_copy(update={'category_id':'running'})
    with pytest.raises(ValueError,match='changed'):clusters.export_cluster(store,work,altered)
    changed=copy.deepcopy(work);changed['model']['k']+=1
    with pytest.raises(ValueError,match='changed'):clusters.export_cluster(store,changed,body)
    changed=copy.deepcopy(work);changed['windows'][0]['group']=7
    with pytest.raises(ValueError,match='changed'):clusters.export_cluster(store,changed,body)
    monkeypatch.setattr(clusters,'STUDIES',STUDIES+[{'id':'paper:new'}])
    with pytest.raises(ValueError,match='changed'):clusters.export_cluster(store,work,body)


def test_cluster_api_requires_review_and_exports_full_group(store,match_workspace):
    work,_=match_workspace;client=TestClient(create_app(store.root));base='/api/cluster-workspaces/'+work['id']
    assert client.get(base).status_code==200
    assert 'raw_audit' not in client.get(base).json()
    assert client.post(base+'/explain',json={'cluster_id':0,'provider':'local'}).status_code==400
    body={'cluster_id':0,'reviewed':True,'category_id':'mixed'}
    result=client.post(base+'/explain',json=body|{'provider':'local'});assert result.status_code==200,result.text
    bid=result.json()['explanation_id']
    job=client.post(base+'/reports',json=body|{'explanation_id':bid}).json()['job_id']
    result=client.get('/api/jobs/'+job).json();assert result['status']=='done',result
    assert client.get('/api/reports/'+result['result']['report_id']+'/download').status_code==200
