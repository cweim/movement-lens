import copy
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from movement_lens import cloud
from movement_lens.app import create_app
from movement_lens.exploration import create_exploration, match_examples, search
from movement_lens.reviews import PatternExplainRequest, review_facts
from test_cloud import install_fake_foundry


def catalogue(store, cohort):
    ref, query, _ = cohort
    xid = create_exploration(store, [ref, query], [ref], 2)['exploration_id']
    return store.read('explorations', xid)


def test_match_scope_includes_both_halves_and_never_other_games(store, cohort):
    c = copy.deepcopy(catalogue(store, cohort));base = c['windows'][0]
    c['windows'] = [base | dict(key='seed',source_hash='a',match_id='game',start=0,end=2),
                    base | dict(key='same-half',source_hash='a',match_id='game',start=5,end=7),
                    base | dict(key='second-half',source_hash='b',match_id='game',start=0,end=2),
                    base | dict(key='different-game',source_hash='c',match_id='other',start=0,end=2)]
    c['vectors'] = [[0.,0.]]*4
    meta = dict(match='test',duration=30,usable_intervals=[[0,2]],retained_intervals=[[0,2]],usable_seconds=2,window_count=1)
    c['sources'] = [meta | dict(id=k,match_id='game' if k in 'ab' else 'other') for k in 'abc']
    r=search(c,'seed',0,same_match_only=True)
    assert {w['key'] for w in r['hits']}=={'same-half','second-half'}
    assert {s['id'] for s in r['timelines']}=={'a','b'}
    assert r['matching_seconds']==4 and r['bouts']==2
    assert r['eligible_count']==2
    with pytest.raises(ValueError,match='not both'):
        search(c,'seed',0,True,True)


def test_examples_are_match_scoped_and_curated_examples_are_declared(store, cohort):
    c=catalogue(store,cohort);seed=c['windows'][0];other=next(w for w in c['windows'] if w['match_id']!=seed['match_id'])
    groups=match_examples(c,seed['match_id'],[other['key'],seed['key']])
    shown=[w for g in groups for w in g['examples']]
    assert shown and all(w['match_id']==seed['match_id'] for w in shown)
    assert other['key'] not in {w['key'] for w in shown}
    target=next(g for g in groups if g['id']==seed['group'])
    assert target['curated'] and target['examples'][0]['key']==seed['key']
    assert sum(g['count'] for g in groups)==sum(w['match_id']==seed['match_id'] for w in c['windows'])


def test_movement_explanation_is_frozen_exported_and_cannot_attach_to_changed_selection(monkeypatch,store,cohort):
    c=catalogue(store,cohort);seed=c['windows'][0]['key'];r=search(c,seed,10000,same_match_only=True);hit=r['hits'][0]['key']
    def fake(facts,question,movement_only=False):
        assert movement_only and facts['search']['same_match_only']
        assert len(facts['profiles'])==1 and facts['movement']['features']
        return {'provider':'foundry','model':'unit-mini','summary':'A real saved AI draft for this selection.',
                'observations':[{'text':'The projected knee differs between these examples.','evidence_ids':[seed,hit]}],
                'limitations':['Camera viewpoint matters.'],'evidence_ids':[seed,hit],'tool_trace':['get_pattern_timeline','get_region_evidence']}
    monkeypatch.setattr(cloud,'foundry_pattern_explain',fake)
    client=TestClient(create_app(store.root));base=f'/api/explorations/{c["id"]}'
    body={'seed_key':seed,'radius':10000,'same_match_only':True,'comparison_key':hit,'selected_keys':[hit],'movement_only':True}
    response=client.post(base+'/movement-explanation',json=body|{'provider':'foundry','question':'Explain the posture'})
    assert response.status_code==200,response.text
    explanation=response.json();bid=explanation['explanation_id']
    saved=store.read('explanations',bid)
    result=client.post(base+'/reviews',json=body|{'explanation_id':bid})
    assert result.status_code==200,result.text
    vid=result.json()['review_id'];review=store.read('reviews',vid)
    assert review['explanation']==saved['result'] and review['provenance']['assistant']['model']=='unit-mini'
    job=client.post(f'/api/reviews/{vid}/reports',json={'include_media':False}).json()['job_id']
    result=client.get('/api/jobs/'+job).json();assert result['status']=='done',result
    rid=result['result']['report_id']
    with zipfile.ZipFile(store.path('reports',rid)/'report.zip') as z:
        doc=z.read('report.html').decode()
        assert 'A real saved AI draft for this selection.' in doc
        assert 'Microsoft Foundry' in doc and 'unit-mini' in doc
        assert 'Staff-entered recovery context' not in doc and 'reviewer: not supplied' not in doc
        assert 'Movement evidence pack' in doc and 'Scope: this match' in doc
        assert json.loads(z.read('provenance.json'))['assistant']['id']==bid
    assert store.read('explanations',bid)==saved
    changed=client.post(base+'/reviews',json=body|{'radius':9999,'explanation_id':bid})
    assert changed.status_code==400 and 'selection changed' in changed.json()['detail']


def test_movement_ai_uses_no_staff_context_tool_and_still_restricts_citations(monkeypatch,store,cohort):
    c=catalogue(store,cohort);seed=c['windows'][0]['key']
    facts=review_facts(c,PatternExplainRequest(seed_key=seed,radius=10000,same_match_only=True,movement_only=True))
    final={'summary':'The projected 2D leg posture varies.', 'observations':[{'text':'Inspect the visible leg bend.','evidence_ids':[seed]}], 'limitations':['Viewpoint affects projected angles.']}
    call=SimpleNamespace(type='function_call',name='get_pattern_timeline',arguments='{}',call_id='movement')
    requests=[]
    region=SimpleNamespace(type='function_call',name='get_region_evidence',arguments='{}',call_id='pair')
    install_fake_foundry(monkeypatch,[SimpleNamespace(output=[call]),SimpleNamespace(output=[region]),SimpleNamespace(output=[],output_text=json.dumps(final))],requests=requests)
    result=cloud.foundry_pattern_explain(facts,'Explain this movement',movement_only=True)
    assert result['provider']=='foundry' and result['tool_trace']==['get_pattern_timeline','get_region_evidence']
    assert requests[1]['tool_choice']=={'type':'function','name':'get_region_evidence'}
    assert all('get_recovery_context' not in {t['name'] for t in r['tools']} for r in requests)
    allowed=requests[1]['text']['format']['schema']['properties']['observations']['items']['properties']['evidence_ids']['items']['enum']
    assert 'staff_context' not in allowed and seed in allowed
