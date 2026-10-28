"""One-match clustering, whole-cluster evidence, reviewed categories and exports."""
import html
import json
import shutil
import subprocess
import time
import uuid
import zipfile
from collections import Counter

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from threadpoolctl import threadpool_limits

from .analysis import source_groups
from .exploration import create_exploration, independent
from .features import FEATURES, LABELS, interval_union
from .store import digest, sha_file
from .reports import csv_bytes
from .cluster_research import CATEGORIES, STUDIES, VERSION as RESEARCH_VERSION

VERSION='one-match-clusters-v1'
COLORS=['#286b50','#b0a35a','#6e8ca4','#a6788d','#7e77a1','#60a39c','#b57d53','#879e65']


class ClusterSelection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cluster_id:int=Field(ge=0,le=7)
    category_id:Literal['descriptive','running','stepping','turning','mixed']='descriptive'
    reviewed:bool=False
    explanation_id:str|None=Field(default=None,pattern=r'^b_[a-f0-9]{24}$')


class ClusterExplainRequest(ClusterSelection):
    provider:Literal['foundry','local']='foundry'


def duration(intervals):
    return round(sum(b-a for a,b in interval_union(intervals)),4)


def choose_match(store):
    path=store.root/'prepared/cluster-match-audit.json'
    audit=json.loads(path.read_text()) if path.is_file() else None
    if audit:
        datasets=[store.read('datasets',did) for did in audit['dataset_ids']]
        for half in audit['halves']:
            ds=next(d for d in datasets if d['id']==half['dataset_id'])
            if ds['source']['sha256']!=half['source_hash'] or ds['usable_count']!=half['usable_windows']:
                raise ValueError('The match preparation changed; refresh its candidate audit before clustering')
        return datasets,audit
    latest={}
    for d in store.list('datasets'):
        if d['usable_count']:
            latest.setdefault((d['player'].casefold(),d['source']['sha256']),d)
    matches={}
    for d in latest.values():
        mid=next(x for x in source_groups(d) if x.startswith('match:'))
        matches.setdefault((d['player'].casefold(),mid),[]).append(d)
    if not matches:
        raise ValueError('Import a verified Touchline player-window dataset before opening the match workspace.')
    datasets=max(matches.values(),key=lambda ds:sum(d['usable_count'] for d in ds))
    return datasets,None


def build_workspace(store,progress=lambda *_:None):
    datasets,audit=choose_match(store)
    mid={next(x for x in source_groups(d) if x.startswith('match:')) for d in datasets}
    if len(mid)!=1 or len({d['player'].casefold() for d in datasets})!=1:
        raise ValueError('The cluster workspace must contain exactly one player in one match')
    mid=next(iter(mid))
    progress('Choosing K using this match only',.1)
    result=create_exploration(store,[d['id'] for d in datasets],progress=progress)
    c=store.read('explorations',result['exploration_id'])
    identity='c_'+digest([VERSION,c['id'],digest(audit) if audit else None])[:24]
    try:
        store.read('cluster_workspaces',identity)
        return {'workspace_id':identity,'cached':True}
    except KeyError:pass
    names=c['model']['feature_names'];z=np.array(c['vectors']);values=np.array(c['values'])
    fit_keys=set(c['model']['fit_windows']);fit_idx=[i for i,w in enumerate(c['windows']) if w['key'] in fit_keys]
    metrics=[]
    with threadpool_limits(limits=1):
        for metric in c['model']['metrics']:
            k=metric['k'];one=KMeans(n_clusters=k,n_init=10,random_state=17).fit(z[fit_idx]);two=KMeans(n_clusters=k,n_init=10,random_state=41).fit(z[fit_idx])
            metrics.append(metric|{'initialization_ARI':float(adjusted_rand_score(one.labels_,two.labels_))})
    sources=[]
    for source in c['sources']:
        d=next(d for d in datasets if d['source']['sha256']==source['id'])
        half=next((h['half'] for h in audit['halves'] if h['source_hash']==source['id']),None) if audit else None
        if half is None:
            half=2 if 'second' in d['match'].casefold() else 1
        offset=(audit or {}).get('clock',{}).get('source_offsets',{}).get(source['id'],2700 if half==2 else 0)
        sources.append(source|{'half':half,'clock_offset':offset})
    sources.sort(key=lambda s:(s['half'],s['id']))
    windows=[]
    for w in c['windows']:
        src=next(s for s in sources if s['id']==w['source_hash'])
        windows.append(w|{'half':src['half'],'match_start':w['start']+src['clock_offset'],'match_end':w['end']+src['clock_offset'],'independent':w['key'] in fit_keys})
    total_seconds=round(sum(duration([[w['start'],w['end']] for w in windows if w['source_hash']==s['id'] and w['independent']]) for s in sources),4)
    clusters=[]
    for group in c['groups']:
        ids=[i for i,w in enumerate(windows) if w['group']==group['id']];ii=[i for i in ids if windows[i]['independent']]
        center=np.array(c['model']['centers'][group['id']]);ranked=sorted(ii,key=lambda i:float(np.linalg.norm(z[i]-center)))
        typical=[];tracks=set()
        for i in ranked:
            w=windows[i];key=(w['source_hash'],w['tracklet_id'])
            if key in tracks:continue
            typical.append(w['key']);tracks.add(key)
            if len(typical)==3:break
        boundary=next((windows[i]['key'] for i in reversed(ranked) if windows[i]['key'] not in typical),None)
        stats=[{'feature':name,'label':LABELS[name],'median':float(np.median(values[ii,n])),
                'p10':float(np.percentile(values[ii,n],10)),'p90':float(np.percentile(values[ii,n],90)),
                'iqr':float(np.percentile(values[ii,n],75)-np.percentile(values[ii,n],25))} for n,name in enumerate(names)]
        intervals=[{'source_hash':s['id'],'half':s['half'],'intervals':interval_union([[windows[i]['start'],windows[i]['end']] for i in ii if windows[i]['source_hash']==s['id']])} for s in sources]
        seconds=round(sum(duration(x['intervals']) for x in intervals),4)
        others=[i for i in fit_idx if i not in ii]
        shifts=sorted([{'feature':name,'label':LABELS[name],'median':float(np.median(values[ii,n])),
                        'other_median':float(np.median(values[others,n])),
                        'standardized_difference':float((np.median(values[ii,n])-np.median(values[others,n]))/c['model']['scale'][n])} for n,name in enumerate(names)],key=lambda x:abs(x['standardized_difference']),reverse=True)
        quality=[]
        for i in ii:
            w=windows[i];d=next(d for d in datasets if d['id']==w['dataset_id']);quality.append(next(x['quality'] for x in d['windows'] if x['id']==w['id']))
        clusters.append({'id':group['id'],'name':f'Cluster {group["id"]+1}','color':COLORS[group['id']],
                         'window_count':len(ids),'independent_count':len(ii),'observed_seconds':seconds,
                         'share_of_observed':seconds/total_seconds if total_seconds else 0.,
                         'tracklet_count':len({(windows[i]['source_hash'],windows[i]['tracklet_id']) for i in ii}),
                         'representatives':typical,'boundary':boundary,'features':stats,'distinguishing_features':shifts[:4],
                         'intervals':intervals,'merged_intervals':sum(len(x['intervals']) for x in intervals),
                         'half_counts':{str(s['half']):sum(windows[i]['source_hash']==s['id'] for i in ii) for s in sources},
                         'quality':{'median_original_joint_visibility':float(np.median([q['minimum_original_joint_visibility'] for q in quality])),
                                    'identity_review':dict(Counter(q['identity_provenance'] for q in quality))}})
    for g in clusters:
        knees=[s['median'] for s in g['features'] if s['feature'] in ('left_knee_median','right_knee_median')]
        g['knee_angle_summary']=float(np.mean(knees)) if knees else None
    if len(clusters)==2 and all(g['knee_angle_summary'] is not None for g in clusters):
        lower=min(clusters,key=lambda g:g['knee_angle_summary'])['id']
        for g in clusters:g['description']='More bent and variable projected leg positions' if g['id']==lower else 'Straighter projected leg positions'
    else:
        for g in clusters:g['description']='A numerical group of projected movement measurements'
    bins=[]
    for start in range(0,5400,300):
        part=[w for w in windows if w['independent'] and w['match_start']<start+300 and w['match_end']>start]
        bins.append({'start':start,'end':start+300,'observed_seconds':round(sum(max(0,min(w['match_end'],start+300)-max(w['match_start'],start)) for w in part),4),
                     'cluster_seconds':{str(g['id']):round(sum(max(0,min(w['match_end'],start+300)-max(w['match_start'],start)) for w in part if w['group']==g['id']),4) for g in clusters}})
    summary={k:v for k,v in (audit or {}).items() if k not in ('windows','halves')}
    if audit:summary['halves']=[{k:v for k,v in h.items() if k!='windows'} for h in audit['halves']]
    work={'id':identity,'created':time.time(),'version':VERSION,'catalogue_id':c['id'],'player':c['player'],'match_id':mid,
          'match':mid.removeprefix('match:'),'windows':windows,'clusters':clusters,'sources':sources,'bins':bins,
          'observed_seconds':total_seconds,'independent_windows':len(fit_idx),'eligible_windows':len(windows),
          'model':c['model']|{'metrics':metrics,'selection':'Highest silhouette among K=2–8 tested on this match; supporting diagnostics and visual review remain necessary.'},
          'dataset_provenance':c['dataset_provenance'],'audit':summary,'raw_audit':audit,
          'clock':(audit or {}).get('clock',{'basis':'unverified_source_half','uncertainty_seconds':None}),
          'limitations':c['limitations']+['Cluster shares describe observed footage, not whole-match workload.','Reviewed categories are human interpretations, not validated action classes.']}
    store.write('cluster_workspaces',identity,work);progress('Match clusters ready',1)
    return {'workspace_id':identity}


def public_workspace(work):
    return {k:v for k,v in work.items() if k!='raw_audit'}


def cluster_evidence(work,body):
    group=next((g for g in work['clusters'] if g['id']==body.cluster_id),None)
    if group is None:raise ValueError('Choose an available cluster')
    if not body.reviewed:raise ValueError('Inspect the examples and confirm a descriptive category first')
    category=next(c for c in CATEGORIES if c['id']==body.category_id)
    keys=[*group['representatives']]+([group['boundary']] if group['boundary'] else [])
    examples=[next(w for w in work['windows'] if w['key']==key) for key in keys]
    return {'workspace_id':work['id'],'cluster_id':group['id'],'cluster_evidence_id':f'cluster:{work["id"]}:{group["id"]}',
            'match':work['match'],'player':work['player'],'group':group,'examples':examples,
            'reviewed_category':category|{'status':'user_confirmed_visual_interpretation'},
            'observed_seconds_total':work['observed_seconds'],'bins':work['bins'],'clock':work['clock'],
            'research':STUDIES,'research_version':RESEARCH_VERSION,'limitations':work['limitations']}


def evidence_signature(work,body):
    return digest([VERSION,work['id'],work['model'],[(w['key'],w['group']) for w in work['windows']],body.cluster_id,body.category_id,body.reviewed,RESEARCH_VERSION,STUDIES])


def example_images(store,work,facts):
    """Bounded three-frame strips for examples, cached by actual clip bytes."""
    if not shutil.which('ffmpeg'):return []
    root=store.path('cluster_workspaces',work['id'])/'images';root.mkdir(exist_ok=True)
    images=[]
    for w in facts['examples']:
        if not w['media']:continue
        clip=store.path('datasets',w['dataset_id'])/'media'/w['media'];sha=sha_file(clip)
        dest=root/(sha[:24]+'.jpg')
        if not dest.is_file():
            temp=dest.with_suffix('.partial.jpg')
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(clip),'-vf',"select='eq(n,0)+eq(n,20)+eq(n,40)',scale=128:256,tile=3x1",'-frames:v','1','-q:v','3',str(temp)],check=True,capture_output=True,timeout=20)
            temp.replace(dest)
        images.append({'window_key':w['key'],'path':str(dest),'clip_sha256':sha,'sha256':sha_file(dest),'frames_relative_seconds':[0,.8,1.6]})
    return images


def save_cluster_explanation(store,work,body,result,images):
    identity='b_'+uuid.uuid4().hex[:24]
    saved={'id':identity,'created':time.time(),'kind':'cluster','workspace_id':work['id'],
           'signature':evidence_signature(work,body),'request':body.model_dump(exclude={'explanation_id'}),
           'research_version':RESEARCH_VERSION,'visuals':images,'result':result}
    store.write('explanations',identity,saved)
    return result|{'explanation_id':identity}


def local_cluster_brief(facts):
    cid=facts['cluster_evidence_id'];g=facts['group']
    return {'provider':'local','summary':g['description']+'. Review the examples alongside the aggregate measurements.',
            'observed':[{'text':f'This cluster contains {g["independent_count"]} independent windows and {g["observed_seconds"]:.0f} observed seconds.', 'evidence_ids':[cid]}],
            'physical_demands':[{'text':'A descriptive pose group alone does not establish a specific action, muscle loading or excessive exposure.','evidence_ids':[cid]}],
            'recovery_context':[{'text':'Football recovery studies concern measured actions and post-match responses; these cluster counts do not establish a player-specific recovery requirement.','evidence_ids':['paper:nedelec2014','paper:kinugasa2009']}],
            'limitations':facts['limitations'],'tool_trace':[],'evidence_ids':[cid,*[p['id'] for p in STUDIES]],'images_sent':0}


def export_cluster(store,work,body,progress=lambda *_:None):
    facts=cluster_evidence(work,body);explanation=local_cluster_brief(facts);assistant=None
    if body.explanation_id:
        assistant=store.read('explanations',body.explanation_id)
        if assistant.get('kind')!='cluster' or assistant.get('signature')!=evidence_signature(work,body):
            raise ValueError('The cluster, reviewed category or research version changed. Generate a fresh explanation before export.')
        for visual in assistant['visuals']:
            w=next(w for w in work['windows'] if w['key']==visual['window_key'])
            if sha_file(store.path('datasets',w['dataset_id'])/'media'/w['media'])!=visual['clip_sha256']:
                raise ValueError('An example clip changed; generate a fresh explanation')
        explanation=assistant['result']
    group=facts['group'];members=[w for w in work['windows'] if w['group']==group['id']]
    identity='r_'+uuid.uuid4().hex[:24];directory=store.path('reports',identity);directory.mkdir()
    esc=lambda x:html.escape(str(x),quote=True)
    articles=[];media={}
    for i,w in enumerate(facts['examples']):
        player=''
        if w['media']:
            path=store.path('datasets',w['dataset_id'])/'media'/w['media'];name=f'media/{w["dataset_id"]}-{w["id"]}.mp4';media[name]=path
            player=f'<video controls preload="metadata" src="{esc(name)}"></video>'
        articles.append(f'<article><h3>{"Typical example" if w["key"] in group["representatives"] else "Less-typical example"}</h3>{player}<p>Half {w["half"]} · {w["start"]:.2f}–{w["end"]:.2f}s source time</p><small>{esc(w["key"])}</small></article>')
    if sum(p.stat().st_size for p in media.values())>512*1024**2:raise ValueError('Representative media exceeds the report limit')
    evidence={facts['cluster_evidence_id']:'Cluster aggregate'}|{w['key']:f'Example · half {w["half"]} · {w["start"]:.2f}s' for w in facts['examples']}|{p['id']:p['title'] for p in STUDIES}
    sections=[]
    for key,title in [('observed','Observed cluster pattern'),('physical_demands','Possible physical demands'),('recovery_context','General recovery context')]:
        text=''.join('<p>'+esc(o['text'])+'</p><small>'+esc(' · '.join(evidence.get(e,e) for e in o['evidence_ids']))+'</small>' for o in explanation[key])
        sections.append(f'<section><h2>{title}</h2>{text}</section>')
    timeline=[]
    for src in work['sources']:
        duration_source=src['duration'] or 2700
        rects=''.join(f'<rect x="{w["start"]/duration_source*1000:.2f}" width="{max(.7,(w["end"]-w["start"])/duration_source*1000):.2f}" y="3" height="24" fill="{work["clusters"][w["group"]]["color"]}" opacity="{1 if w["group"]==group["id"] else .2}"/>' for w in work['windows'] if w['source_hash']==src['id'] and w['independent'])
        timeline.append(f'<h3>Half {src["half"]} · exact source-relative time</h3><svg viewBox="0 0 1000 30"><rect width="1000" height="30" fill="#edf0e7"/>{rects}</svg><p>0 to {duration_source/60:.2f} source minutes. Blank intervals are unobserved.</p>')
    statistics=''.join(f'<tr><td>{esc(s["label"])}</td><td>{s["median"]:.2f}</td><td>{s["p10"]:.2f}–{s["p90"]:.2f}</td></tr>' for s in group['features'])
    references=''.join(f'<li><a href="{esc(p["url"])}">{esc(p["title"])}</a> · {esc(p["design"])}<p>{esc(p["finding"])}</p><small>{esc(p["limits"])}</small></li>' for p in STUDIES)
    document=f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Movement Lens cluster evidence</title><style>body{{font:15px/1.7 system-ui;background:#f7f9f3;color:#254435;max-width:1100px;margin:auto;padding:28px}}section,article{{background:white;border:1px solid #dfe7d7;border-radius:12px;padding:20px;margin:18px 0}}.clips{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}video{{width:100%;height:280px;background:#17291f}}svg{{width:100%}}small{{color:#7c8e6e}}td,th{{text-align:left;padding:8px;border-bottom:1px solid #e4ebdc}}table{{border-collapse:collapse;width:100%}}</style><h1>Movement Lens · {esc(group['name'])}</h1><p>{esc(work['player'])} · {esc(work['match'])}</p><p>Reviewed as: {esc(facts['reviewed_category']['label'])} · user-confirmed visual interpretation</p><p>{group['independent_count']} independent windows · {group['observed_seconds']:.0f}s · {group['share_of_observed']*100:.1f}% of observed player footage. Gaps remain unknown; intervals are not physical repetitions.</p><section><h2>Cluster explanation</h2><small>{'Microsoft Foundry · AI draft' if explanation['provider']=='foundry' else 'Computed evidence snapshot'}</small><p>{esc(explanation['summary'])}</p></section>{''.join(sections)}<section><h2>Whole-match cluster distribution</h2>{''.join(timeline)}<p>Match-minute labels in the app are approximate; source timestamps in this report are exact.</p></section><div class="clips">{''.join(articles)}</div><details><summary>Aggregate measurements, research and limitations</summary><table><tr><th>Descriptor</th><th>Median</th><th>p10–p90</th></tr>{statistics}</table><ul>{references}</ul><ul>{''.join('<li>'+esc(x)+'</li>' for x in explanation['limitations'])}</ul><p>AI educational context does not establish muscle loading, fatigue, injury, treatment or recovery duration for this player.</p></details>'''
    frozen={'workspace_id':work['id'],'cluster':group,'category':facts['reviewed_category'],'members':members,'explanation':explanation,
            'provenance':{'version':VERSION,'model':work['model'],'datasets':work['dataset_provenance'],'research_version':RESEARCH_VERSION,
                          'explanation_id':body.explanation_id,'assistant':({k:assistant[k] for k in ('created','visuals','research_version')} | {k:explanation.get(k) for k in ('provider','model','tool_trace','evidence_ids','images_sent')}) if assistant else None,'clock':work['clock']}}
    rows=[{k:w[k] for k in ('key','dataset_id','id','half','start','end','match_start','match_end','independent','group')} for w in members]
    progress('Packaging the cluster evidence and representative clips',.5)
    path=directory/'report.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('report.html',document);z.writestr('report.json',json.dumps(frozen,allow_nan=False));z.writestr('provenance.json',json.dumps(frozen['provenance'],allow_nan=False))
        z.writestr('cluster-members.csv',csv_bytes(rows));z.writestr('aggregate-features.csv',csv_bytes(group['features']));z.writestr('k-diagnostics.csv',csv_bytes(work['model']['metrics']));z.writestr('timeline.json',json.dumps({'sources':work['sources'],'windows':work['windows'],'bins':work['bins']}))
        if work.get('raw_audit'):z.writestr('candidate-audit.json',json.dumps(work['raw_audit']))
        for name,source in media.items():z.write(source,name)
    record={'id':identity,'created':time.time(),'kind':'cluster','workspace_id':work['id'],'cluster_id':group['id'],'bytes':path.stat().st_size,'sha256':sha_file(path),'representative_clips':len(media),'explanation_id':body.explanation_id}
    (directory/'report.html').write_text(document);store.write('reports',identity,record);progress('Cluster evidence pack ready',1)
    return {'report_id':identity}
