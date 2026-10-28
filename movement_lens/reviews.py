"""Staff-entered recovery context, frozen reviews and portable evidence reports."""
import html
import json
import time
import uuid
import zipfile
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

from .exploration import compare_regions, search, find_index
from .research import PAPERS
from .reports import csv_bytes, trace_svg
from .store import sha_file, digest


class Symptom(BaseModel):
    model_config = ConfigDict(extra='forbid')
    region: Literal['left_knee', 'right_knee', 'left_hip', 'right_hip', 'trunk', 'left_thigh', 'right_thigh', 'left_calf', 'right_calf', 'other']
    severity: float = Field(ge=0, le=10, allow_inf_nan=False)
    reported_at: str = Field(default='', max_length=100)


class RecoveryContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symptoms: list[Symptom] = Field(default_factory=list, max_length=20)
    assessment_at: str = Field(default='', max_length=100)
    recent_minutes: float | None = Field(default=None, ge=0, le=10080, allow_inf_nan=False)
    session_rpe: float | None = Field(default=None, ge=0, le=10, allow_inf_nan=False)
    hours_since_match: float | None = Field(default=None, ge=0, le=720, allow_inf_nan=False)
    staff_notes: str = Field(default='', max_length=4000)
    decision: str = Field(default='', max_length=4000)
    follow_up: str = Field(default='', max_length=4000)
    reviewer: str = Field(default='', max_length=100)
    status: Literal['draft', 'staff_reviewed'] = 'draft'


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed_key: str = Field(max_length=210)
    radius: float = Field(ge=0, le=10000, allow_inf_nan=False)
    cross_match_only: bool = False
    same_match_only: bool = False
    comparison_key: str | None = Field(default=None, max_length=210)
    selected_keys: list[str] = Field(default_factory=list, max_length=50)
    context: RecoveryContext = Field(default_factory=RecoveryContext)
    movement_only: bool = False
    explanation_id: str | None = Field(default=None, pattern=r'^b_[a-f0-9]{24}$')


class PatternExplainRequest(ReviewRequest):
    provider: Literal['local', 'foundry'] = 'local'
    question: str = Field(default='', max_length=1500)


def review_facts(record, body):
    result = search(record, body.seed_key, body.radius, body.cross_match_only, body.same_match_only)
    hits = {w['key']: w for w in result['hits']}
    selected = list(dict.fromkeys(body.selected_keys))
    if any(k not in hits for k in selected):
        raise ValueError('Curated clips must belong to the current similarity results')
    comparison = body.comparison_key or (result['hits'][0]['key'] if result['hits'] else None)
    if comparison is not None and comparison not in hits:
        raise ValueError('Choose a comparison from the current similarity results')
    if body.context.status == 'staff_reviewed' and not body.context.reviewer.strip():
        raise ValueError('Enter the staff reviewer name before recording a reviewed snapshot')
    return {'exploration_id': record['id'], 'player': record['player'], 'search': result,
            'movement': {'window_key': body.seed_key,
                         'features': dict(zip(record['model']['feature_names'], record['values'][find_index(record, body.seed_key)])),
                         'units': 'Projected angles in degrees; ankle separation divided by torso length.'},
            'profiles': [m for m in record['matches'] if not body.same_match_only or m['id'] == result['seed']['match_id']], 'groups': record['groups'],
            'comparison': compare_regions(record, body.seed_key, comparison) if comparison else None,
            'selected': [hits[k] for k in selected], 'context': body.context.model_dump(),
            'context_origin': 'staff_entered; not inferred from video', 'research': PAPERS,
            'limitations': record['limitations'] + ['Recovery outcomes and clinical interpretation are not inferred by this application.']}


def local_pattern_explanation(facts):
    seed = facts['search']['seed']['key']
    observations = [{'text': 'Inspect matching source intervals and their unobserved gaps before interpreting recurrence.', 'evidence_ids': [seed]},
                    {'text': 'The regional map explains descriptor-distance contributions, not muscle loading or soreness.', 'evidence_ids': [seed, 'paper:opencap2023']},
                    {'text': 'Match-action and recovery studies motivate follow-up measurement; they do not provide an individual treatment rule for these clips.',
                     'evidence_ids': ['paper:nedelec2014', 'paper:tan2025']}]
    return {'provider': 'local', 'summary': 'This brief brings together observed movement, staff-entered context and research for staff review.',
            'observations': observations, 'limitations': facts['limitations'], 'tool_trace': [],
            'evidence_ids': [seed] + [p['id'] for p in PAPERS]}


def local_movement_explanation(facts):
    seed = facts['search']['seed']['key']
    values = facts['movement']['features']
    observations = []
    for side in ('left', 'right'):
        value = values.get(side+'_knee_median')
        if value is not None:
            observations.append({'text': f'The {side} projected knee angle has a median of {value:.1f}° in this clip. A straighter image-plane leg is closer to 180°.', 'evidence_ids': [seed]})
    return {'provider': 'local', 'summary': 'A movement snapshot from the selected clip. Inspect the video and pose together before interpreting these projected measurements.',
            'observations': observations, 'limitations': facts['limitations'], 'tool_trace': [], 'evidence_ids': [seed]}


def selection_signature(body):
    return digest({name: getattr(body, name) if name != 'context' else body.context.model_dump()
                   for name in ReviewRequest.model_fields if name != 'explanation_id'})


def save_explanation(store, record, body, result):
    identity = 'b_' + uuid.uuid4().hex[:24]
    saved = {'id': identity, 'created': time.time(), 'exploration_id': record['id'],
             'selection_signature': selection_signature(body), 'question': body.question, 'result': result}
    store.write('explanations', identity, saved)
    return result | {'explanation_id': identity}


def save_review(store, record, body):
    facts = review_facts(record, body)
    explanation = local_movement_explanation(facts) if body.movement_only else local_pattern_explanation(facts)
    assistant = None
    if body.explanation_id:
        saved = store.read('explanations', body.explanation_id)
        if saved['exploration_id'] != record['id'] or saved['selection_signature'] != selection_signature(body):
            raise ValueError('The movement selection changed. Explain the current selection again before export.')
        explanation = saved['result']
        assistant = {k: saved[k] for k in ('id', 'created', 'question')}
        assistant.update(provider=explanation['provider'], model=explanation.get('model'),
                         evidence_ids=explanation['evidence_ids'], tool_trace=explanation['tool_trace'])
    identity = 'v_' + uuid.uuid4().hex[:24]
    snapshot = {'id': identity, 'created': time.time(), 'exploration_id': record['id'],
                'request': body.model_dump(), 'facts': facts, 'explanation': explanation,
                'provenance': {'feature_version': record['feature_version'], 'catalogue_version': record['version'],
                               'model': record['model'], 'datasets': record['dataset_provenance']}}
    if assistant:
        snapshot['provenance']['assistant'] = assistant
    store.write('reviews', identity, snapshot)
    return {'review_id': identity}


def build_review_report(store, review_id, include_media=False, progress=lambda *_: None):
    review = store.read('reviews', review_id)
    facts = review['facts']; result = facts['search']; ctx = facts['context']
    movement_only = review['request'].get('movement_only', False)
    identity = 'r_' + uuid.uuid4().hex[:24]
    directory = store.path('reports', identity); directory.mkdir()
    esc = lambda x: html.escape(str(x), quote=True)
    articles, media_files = [], {}
    clips = [result['seed'], *facts['selected']]
    for i, clip in enumerate(clips):
        ds = store.read('datasets', clip['dataset_id'])
        w = next(w for w in ds['windows'] if w['id'] == clip['id'])
        video = '<p>Video not included.</p>'
        if include_media and w['media']:
            source = store.path('datasets', ds['id'])/'media'/w['media']
            if not source.is_file():
                raise ValueError('Selected imported media is missing')
            name = f'media/{ds["id"]}-{w["id"]}.mp4'; media_files[name] = source
            video = f'<video controls preload="metadata" src="{esc(name)}"></video>'
        articles.append(f'<article><h3>{"Seed" if i == 0 else "Curated comparison"} · {esc(ds["match"])}</h3><p>{esc(w["original_id"])} · {w["start"]:.2f}–{w["end"]:.2f}s source time</p>{video}{trace_svg(w["traces"].get("left_knee", []))}<small>Projected left knee; plots use their own vertical range. Identity provenance: {esc(w["quality"].get("identity_provenance", "unspecified"))}.</small></article>')
        progress(f'Preparing curated clip {i+1} of {len(clips)}', (i+1)/len(clips)*.7)
    timeline_rows, timeline_html = [], []
    for source in result['timelines']:
        end = source['duration'] or max([b for _, b in source['usable_intervals']] + [1])
        rects = ''.join(f'<rect x="{a/end*1000:.3f}" y="2" width="{max(.5,(b-a)/end*1000):.3f}" height="18" fill="#cbdacf"/>' for a,b in source['usable_intervals'])
        rects += ''.join(f'<rect x="{a/end*1000:.3f}" y="2" width="{max(.8,(b-a)/end*1000):.3f}" height="18" fill="#216f55"/>' for a,b in source['matching_intervals'])
        timeline_html.append(f'<p><strong>{esc(source["match"])}</strong> · source {source["id"][:8]}</p><svg viewBox="0 0 1000 22" aria-label="Usable and matching source intervals"><rect width="1000" height="22" fill="#edf0eb"/>{rects}</svg><p>{source["matched_windows"]} matching windows · {source["bouts"]} bouts · {source["matching_seconds"]:.2f}s matching / {source["usable_seconds"]:.2f}s usable observed footage</p>')
        timeline_rows.append({k:source[k] for k in ('id', 'match', 'matched_windows', 'bouts', 'matching_seconds', 'usable_seconds', 'share_of_usable_observed_time')})
    regions = facts['comparison']['regions'] if facts['comparison'] else []
    region_html = ''.join(f'<tr><td>{esc(r["label"])}</td><td>{r["share"]*100:.1f}%</td></tr>' for r in regions)
    profiles = [dict(match=m['name'], sampled_windows=m['sample_windows'], sampled_seconds=m['sample_seconds'],
                     **{f'group_{g["group"]+1}_share':g['share'] for g in m['groups']}) for m in facts['profiles']]
    context_html = '<ul>'+''.join(f'<li>{esc(s["region"])}: {s["severity"]}/10 · reported {esc(s["reported_at"] or "time not supplied")}</li>' for s in ctx['symptoms'])+'</ul>' if ctx['symptoms'] else '<p>No symptoms supplied.</p>'
    context_html += ''.join(f'<p><strong>{esc(label)}:</strong> {esc(ctx.get(field) if ctx.get(field) is not None and ctx.get(field) != "" else "Not supplied")}</p>' for field,label in
                            [('assessment_at','Staff-reported assessment date/time'),('recent_minutes','Reported match/training minutes in last seven days'),('session_rpe','Reported session RPE'),('hours_since_match','Reported hours since match'),
                             ('staff_notes','Staff notes'),('decision','Staff decision'),('follow_up','Follow-up plan')])
    research_html = ''.join(f'<li><a href="{esc(p["url"])}">{esc(p["title"])}</a>: {esc(p["summary"])} {esc(p["applicability"])}</li>' for p in PAPERS)
    staff_section = '' if movement_only else '<section><h2>Staff-entered recovery context</h2>'+context_html+'</section>'
    title = 'Movement evidence pack' if movement_only else 'Recovery review'
    assistant = review['provenance'].get('assistant')
    explanation_origin = ('Microsoft Foundry · AI-assisted draft · '+esc(assistant.get('model') or 'configured model')) if assistant and assistant['provider']=='foundry' else 'Computed movement snapshot'
    lookup = {w['key']:w for w in [result['seed'],*result['hits']]}
    def citation_label(identity):
        if identity in lookup:
            w = lookup[identity]
            return f'{w["match"]} · {int(w["start"]//60)}:{w["start"]%60:05.2f} source time'
        paper = next((p for p in PAPERS if p['id']==identity),None)
        return paper['title'] if paper else identity
    explanation_html = ''.join('<p>'+esc(o['text'])+'</p><small>'+esc(' · '.join(citation_label(k) for k in dict.fromkeys(o['evidence_ids'])))+'</small>' for o in review['explanation']['observations'])
    signoff = 'Selected clips, observed recurrence and movement observations.' if movement_only else esc(ctx['status'].replace('_',' '))+' · reviewer: '+esc(ctx['reviewer'] or 'not supplied')
    doc = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Movement Lens · {title}</title>
<style>body{{font:15px/1.65 system-ui;color:#203b30;background:#f5f6f1;max-width:1100px;margin:auto;padding:32px}}section,article{{background:white;border:1px solid #dde5da;border-radius:16px;padding:22px;margin:18px 0}}.clips{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}}video{{width:100%;height:280px;object-fit:contain;background:#17281f}}svg{{width:100%}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid #dde5da;text-align:left}}small{{color:#657960}}p,li{{overflow-wrap:anywhere}}</style>
<h1>Movement Lens · {title}</h1><p>{esc(facts['player'])} · {signoff}</p>
<p>This is movement evidence for staff review. It does not estimate muscle damage, required treatment or recovery duration. Source time is separate from the match clock.</p>
<section><h2>Comparable moments</h2><p>Radius {result['radius']:.4f} · {result['matched_windows']} candidate clips · {result['bouts']} merged source intervals · {result['matching_seconds']:.2f}s. Seed and overlapping seed observations excluded. Scope: {'this match' if result.get('same_match_only') else 'other matches' if result['cross_match_only'] else 'imported library'}.</p>{''.join(timeline_html)}<p>Shares use usable observed footage; gaps remain unknown. Bouts are not physical repetitions.</p></section>
<section><h2>Regional descriptor differences</h2><p>Contribution to squared standardized descriptor distance for the selected pair, not a muscle or injury heatmap.</p><table><tr><th>Region</th><th>Contribution</th></tr>{region_html}</table></section>
<div class="clips">{''.join(articles)}</div>{staff_section}
<section><h2>Movement observations</h2><small>{explanation_origin}</small><p>{esc(review['explanation']['summary'])}</p>{explanation_html}</section>
<details><summary>Research context and method limits</summary><ul>{research_html}</ul><ul>{''.join('<li>'+esc(x)+'</li>' for x in facts['limitations'])}</ul><p>Exact settings, snapshot hashes, citation IDs and explanation provenance are retained in the JSON files. AI text is an observational draft, not a diagnosis or treatment recommendation.</p></details></html>'''
    if sum(p.stat().st_size for p in media_files.values()) > 512*1024**2:
        raise ValueError('Selected media exceeds the 512 MB report limit')
    path = directory/'report.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('report.html', doc)
        z.writestr('report.json', json.dumps(review, allow_nan=False))
        z.writestr('provenance.json', json.dumps(review['provenance'], allow_nan=False))
        z.writestr('recurrence.csv', csv_bytes(timeline_rows))
        z.writestr('matching-windows.csv', csv_bytes([{k:w.get(k) for k in ('key','original_id','match','start','end','distance','group')} for w in result['hits']]))
        z.writestr('match-profiles.csv', csv_bytes(profiles))
        z.writestr('body-regions.csv', csv_bytes([{'region':r['id'], 'label':r['label'], 'distance_share':r['share']} for r in regions]))
        for name, source in media_files.items():
            z.write(source, name)
    (directory/'report.html').write_text(doc)
    store.write('reports', identity, {'id':identity, 'created':time.time(), 'exploration_id':review['exploration_id'],
                                     'review_id':review_id, 'review_status':ctx['status'], 'selected_count':len(clips),
                                     'bytes':path.stat().st_size, 'sha256':sha_file(path), 'include_media':include_media})
    return {'report_id':identity}
