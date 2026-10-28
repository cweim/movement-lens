"""Portable reports: exact evidence and optional explicitly included media."""
import csv
import html
import io
import json
import time
import uuid
import zipfile

from .analysis import evidence, explain
from .features import BONES
from .store import sha_file


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
    return stream.getvalue()


def trace_svg(values):
    valid = [v for v in values if v is not None]
    if not valid:
        return ''
    lo, hi = min(valid), max(valid)
    parts, current = [], []
    for i, v in enumerate(values):
        if v is None:
            if current:
                parts.append(current)
                current = []
        else:
            current.append(f'{i/49*400:.2f},{90-(v-lo)/max(hi-lo,1)*70:.2f}')
    if current:
        parts.append(current)
    return '<svg viewBox="0 0 400 110" role="img" aria-label="Projected left knee trace">' + ''.join(
        f'<polyline points="{" ".join(p)}" fill="none" stroke="#18816a" stroke-width="2"/>' for p in parts) + '</svg>'


def build_report(store, analysis_id, episode_ids, notes=None, include_media=False, progress=lambda *_: None):
    analysis = store.read('analyses', analysis_id)
    ids = list(dict.fromkeys(episode_ids))
    if not ids or len(ids) > 50:
        raise ValueError('Choose between one and 50 episodes for a report')
    notes = notes or {}
    if any(not isinstance(v, str) or len(v) > 2000 for v in notes.values()):
        raise ValueError('Review notes must be at most 2,000 characters each')
    bundles = [evidence(store, analysis_id, i) for i in ids]
    identity = 'r_' + uuid.uuid4().hex[:24]
    directory = store.path('reports', identity)
    directory.mkdir()
    items, media_files, episode_rows, comparison_rows, articles = [], {}, [], [], []
    esc = lambda x: html.escape(str(x), quote=True)
    for index, b in enumerate(bundles):
        e, q = b['episode'], b['query']
        explanation = explain(b)
        item = {'episode': e, 'query': q, 'comparisons': b['comparisons'], 'explanation': explanation,
                'review_note': notes.get(e['id'], ''), 'note_author': 'user' if notes.get(e['id']) else None}
        # No private filesystem paths or browser-only URLs are exported.
        items.append(item)
        episode_rows.append({'episode_id': e['id'], 'query_window_id': q['window']['original_id'], 'source_start': e['start'],
                             'source_end': e['end'], 'distance': e['distance'], 'empirical_rank': e['percentile'],
                             'member_windows': len(e['members']), 'review_note': item['review_note']})
        cards = []
        candidates = [(q['dataset_id'], q['window'], q['match'], 'Query')]
        candidates += [(c['dataset_id'], c['window'], c['match'], 'Reference') for c in b['comparisons']]
        for did, w, match, role in candidates:
            media = ''
            if include_media and w['media']:
                name = f'media/{did}-{w["id"]}.mp4'
                path = store.path('datasets', did) / 'media' / w['media']
                if not path.is_file():
                    raise ValueError('Selected media is missing. Prepare a report without media or restore the imported dataset.')
                media_files[name] = path
                media = f'<video controls preload="metadata" src="{esc(name)}"></video>'
            else:
                media = '<p class="muted">Video is not included in this report.</p>'
            cards.append(f'<div class="clip"><span class="tag">{role}</span><h3>{esc(match)}</h3><p>{w["start"]:.2f}–{w["end"]:.2f}s · {esc(w["original_id"])}</p>{media}{trace_svg(w["traces"].get("left_knee", []))}<small>Projected left-knee trace; each plot uses its own vertical range. Gaps are missing values.</small></div>')
        differences = []
        if b['comparisons']:
            for d in b['comparisons'][0]['differences']:
                comparison_rows.append({'episode_id': e['id'], 'query_window_id': q['window']['original_id'],
                                        'reference_window_id': b['comparisons'][0]['original_id'], **d})
                differences.append(f'<tr><td>{esc(d["label"])}</td><td>{d["query"]:.2f}</td><td>{d["reference"]:.2f}</td></tr>')
        articles.append(f'<section id="{e["id"]}"><h2>Episode {e["rank"]} · {e["start"]:.2f}–{e["end"]:.2f}s</h2><p>Representative two-second window from {len(e["members"])} merged windows. Reference distance: {e["distance"]:.3f}.</p><div class="clips">{"".join(cards)}</div><h3>Observed descriptor differences</h3><table><tr><th>Descriptor</th><th>Query</th><th>Closest reference</th></tr>{"".join(differences)}</table><p>{esc(explanation["summary"])}</p><p><strong>User note:</strong> {esc(item["review_note"] or "None")}</p></section>')
        progress(f'Preparing episode {index+1} of {len(bundles)}', (index+1)/len(bundles)*.8)
    datasets = [store.read('datasets', i) for i in [analysis['query_id'], *analysis['reference_ids']] + ([analysis['calibration']['dataset_id']] if analysis['calibration']['dataset_id'] else [])]
    provenance = {'schema_version': 1, 'analysis_id': analysis_id, 'feature_version': analysis['version'], 'model': analysis['model'],
                  'calibration': analysis['calibration'], 'datasets': [{'id': d['id'], 'archive_sha256': d['archive_sha256'],
                  'source_sha256': d['source']['sha256'], 'snapshot_signature': d['snapshot_signature'], 'match': d['match'],
                  'player': d['player']} for d in datasets], 'media_included': include_media}
    q = bundles[0]['query']
    limitations = analysis['limitations'] + [analysis['calibration']['message'], 'Included examples were selected for review; they are not an unbiased evaluation set.']
    doc = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Movement Lens report</title>
<style>body{{font:15px/1.65 system-ui,sans-serif;background:#f6f8f7;color:#19322b;max-width:1100px;margin:auto;padding:38px}}h1{{font-size:40px;letter-spacing:-1.8px}}h2{{letter-spacing:-.6px}}section{{background:white;border:1px solid #dce5df;border-radius:18px;padding:24px;margin:24px 0}}.clips{{display:flex;gap:20px;overflow:auto}}.clip{{flex:1;min-width:180px}}.clip p,small,.muted{{font-size:12px;color:#60716a;overflow-wrap:anywhere}}video{{width:100%;max-height:300px;background:#10251e}}svg{{width:100%}}table{{width:100%;text-align:left;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #e3ebe6}}.tag{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#16775b}}</style>
<h1>Movement Lens</h1><p>Player movement evidence report · {esc(q['player'])}</p><p>{esc(q['match'])} · {q['coverage']['observed_seconds']:.2f} unique observed seconds. Source-time intervals, not the broadcast match clock.</p>
<p><strong>Reading this report:</strong> it compares projected 2D movements against a selected reference library. It does not estimate injury, fatigue, physical speed or whole-match activity. Clip playback shows the representative window, not every second of a merged episode.</p>{''.join(articles)}<section><h2>Coverage and limitations</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in limitations)}</ul><p>Exact inputs and numerical model parameters are preserved in provenance.json. This report uses local deterministic explanations; any optional live assistant wording remains separate.</p></section></html>'''
    path = directory / 'report.zip'
    if sum(p.stat().st_size for p in media_files.values()) > 512 * 1024**2:
        raise ValueError('Selected report media exceeds 512 MB. Select fewer episodes or export without media.')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('report.html', doc)
        z.writestr('report.json', json.dumps({'schema_version': 1, 'analysis_id': analysis_id, 'items': items, 'limitations': limitations}, allow_nan=False))
        z.writestr('provenance.json', json.dumps(provenance, allow_nan=False))
        z.writestr('episodes.csv', csv_bytes(episode_rows))
        z.writestr('comparisons.csv', csv_bytes(comparison_rows))
        for name, file in media_files.items():
            z.write(file, name)
    (directory / 'report.html').write_text(doc)
    record = {'id': identity, 'created': time.time(), 'analysis_id': analysis_id, 'episode_ids': ids,
              'include_media': include_media, 'bytes': path.stat().st_size, 'sha256': sha_file(path)}
    store.write('reports', identity, record)
    return {'report_id': identity}
