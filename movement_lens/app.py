"""Loopback API and production UI for Movement Lens."""
import json
import uuid
from pathlib import Path

import numpy as np
from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import cloud, azure_datasets
from .analysis import analyse, evidence, explain
from .features import BONES
from .importer import MAX_ZIP_BYTES, import_dataset
from .pose_view import player_pose
from .exploration import create_exploration, public_exploration, search, compare_regions, match_examples
from .reviews import ReviewRequest, PatternExplainRequest, review_facts, local_pattern_explanation, local_movement_explanation, save_explanation, save_review, build_review_report
from .research import PAPERS, REGIONS, region_context
from .reports import build_report
from .store import Store
from . import clusters, cluster_ai
from .cluster_research import CATEGORIES, STUDIES


class AnalysisRequest(BaseModel):
    query_id: str
    reference_ids: list[str] = Field(min_length=1, max_length=30)
    calibration_id: str | None = None


class ExplainRequest(BaseModel):
    audience: str = 'analyst'
    question: str = Field(default='', max_length=1500)
    provider: str = 'local'


class ReportRequest(BaseModel):
    episode_ids: list[str] = Field(min_length=1, max_length=50)
    notes: dict[str, str] = Field(default_factory=dict)
    include_media: bool = False


class ExplorationRequest(BaseModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=30)
    reference_ids: list[str] = Field(default_factory=list, max_length=30)
    clusters: int | None = Field(default=None, ge=2, le=8)


class SearchRequest(BaseModel):
    seed_key: str = Field(max_length=210)
    radius: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    cross_match_only: bool = False
    same_match_only: bool = False


class RegionRequest(BaseModel):
    seed_key: str = Field(max_length=210)
    comparison_key: str = Field(max_length=210)


class SnapshotRequest(BaseModel):
    include_media: bool = False


class AzureImportRequest(BaseModel):
    blob: str = Field(max_length=300)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    etag: str | None = Field(default=None, max_length=200)


def dataset_summary(d):
    return {k: v for k, v in d.items() if k != 'windows'}


def create_app(state=None):
    app = FastAPI(title='Movement Lens', version='0.4.0')
    store = Store(state)
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8770', 'http://localhost:8770', 'http://127.0.0.1:5174', 'http://localhost:5174'}:
            return JSONResponse({'detail': 'Use the local Movement Lens application'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(_, error):
        return JSONResponse({'detail': str(error)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing(_, error):
        return JSONResponse({'detail': str(error).strip("'")}, status_code=404)

    @app.get('/api/status')
    def status():
        presentation = {}
        path = store.root/'prepared/simple-demo.json'
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                presentation = {k: data[k] for k in ('default_match_id', 'curated_examples', 'label') if k in data}
            except (ValueError, TypeError):
                pass
        return {'name': 'Movement Lens', 'version': '0.4.0', 'cloud': cloud.config() | {'azure_import':azure_datasets.configuration()}, 'presentation': presentation}

    @app.get('/api/datasets')
    def datasets():
        return [dataset_summary(d) for d in store.list('datasets')]

    @app.post('/api/cluster-workspace')
    def cluster_workspace_create(tasks: BackgroundTasks):
        jid=store.job('cluster_workspace')
        tasks.add_task(store.run,jid,clusters.build_workspace,store)
        return {'job_id':jid}

    @app.get('/api/cluster-workspaces/{workspace_id}')
    def cluster_workspace_get(workspace_id: str):
        return clusters.public_workspace(store.read('cluster_workspaces',workspace_id)) | {'categories':CATEGORIES,'studies':STUDIES}

    @app.post('/api/cluster-workspaces/{workspace_id}/explain')
    def cluster_explain(workspace_id: str, body: clusters.ClusterExplainRequest):
        work=store.read('cluster_workspaces',workspace_id)
        facts=clusters.cluster_evidence(work,body)
        images=clusters.example_images(store,work,facts) if body.provider=='foundry' else []
        result=cluster_ai.explain_cluster(facts,images) if body.provider=='foundry' else clusters.local_cluster_brief(facts)
        return clusters.save_cluster_explanation(store,work,body,result,images)

    @app.post('/api/cluster-workspaces/{workspace_id}/reports')
    def cluster_report(workspace_id: str, body: clusters.ClusterSelection, tasks: BackgroundTasks):
        work=store.read('cluster_workspaces',workspace_id)
        clusters.cluster_evidence(work,body)
        jid=store.job('cluster_report')
        tasks.add_task(store.run,jid,clusters.export_cluster,store,work,body)
        return {'job_id':jid}

    @app.post('/api/datasets')
    def upload(tasks: BackgroundTasks, file: UploadFile = File(...)):
        path = store.root / 'uploads' / (uuid.uuid4().hex+'.zip')
        try:
            total = 0
            with path.open('wb') as f:
                while part := file.file.read(1024*1024):
                    total += len(part)
                    if total > MAX_ZIP_BYTES:
                        raise ValueError('ZIP exceeds the 1 GB local import limit')
                    f.write(part)
            jid = store.job('import')
            tasks.add_task(store.run, jid, import_dataset, store, path, Path(file.filename or 'dataset.zip').name)
            return {'job_id': jid}
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()

    @app.get('/api/jobs/{job_id}')
    def job(job_id: str):
        return store.read('jobs', job_id)

    @app.get('/api/datasets/{dataset_id}')
    def dataset(dataset_id: str):
        d = store.read('datasets', dataset_id)
        return dataset_summary(d) | {'windows': [{k:v for k,v in w.items() if k != 'traces'} for w in d['windows']]}

    def find_window(dataset_id, window_id):
        d = store.read('datasets', dataset_id)
        w = next((x for x in d['windows'] if x['id'] == window_id), None)
        if w is None:
            raise KeyError('Window not found')
        return w

    @app.get('/api/datasets/{dataset_id}/windows/{window_id}')
    def window(dataset_id: str, window_id: str):
        w = find_window(dataset_id, window_id)
        source = store.read('datasets', dataset_id)['source']
        with np.load(store.path('datasets', dataset_id) / 'arrays' / f'{w["id"]}.npz', allow_pickle=False) as a:
            p = a['keypoints'].astype(float)
            mask = a['valid_mask'].astype(bool) & (a['kp_conf'] >= .3)
            hips = (p[:, 11]+p[:, 12])/2
            centered = p-hips[:, None, :]
            lengths = (np.linalg.norm(p[:, 5]-p[:, 11], axis=1)+np.linalg.norm(p[:, 6]-p[:, 12], axis=1))/2
            points = centered / np.maximum(lengths[:, None, None], 1)
            frames = [[[round(float(v), 4) for v in pt] if mask[i, j] else None for j, pt in enumerate(fr)] for i, fr in enumerate(points)]
            view = player_pose(p, a['bbox'], mask, int(source['width']), int(source['height']))
        return w | {'skeleton': frames, 'pose_view': view, 'bones': BONES,
                    'video_url': f'/api/datasets/{dataset_id}/windows/{window_id}/video' if w['media'] else None}

    @app.get('/api/datasets/{dataset_id}/windows/{window_id}/video')
    def video(dataset_id: str, window_id: str):
        w = find_window(dataset_id, window_id)
        if not w['media']:
            raise KeyError('Video is not included in this export')
        return FileResponse(store.path('datasets', dataset_id) / 'media' / w['media'], media_type='video/mp4')

    @app.post('/api/analyses')
    def new_analysis(body: AnalysisRequest, tasks: BackgroundTasks):
        jid = store.job('analysis')
        tasks.add_task(store.run, jid, analyse, store, body.query_id, body.reference_ids, body.calibration_id)
        return {'job_id': jid}

    @app.get('/api/analyses')
    def analyses():
        return [{k:v for k,v in a.items() if k not in {'model', 'scores', 'episodes'}} | {'episode_count': len(a['episodes'])} for a in store.list('analyses')]

    @app.get('/api/analyses/{analysis_id}')
    def analysis(analysis_id: str):
        a = store.read('analyses', analysis_id)
        return {k:v for k,v in a.items() if k not in {'model'}}

    @app.get('/api/analyses/{analysis_id}/episodes/{episode_id}')
    def episode(analysis_id: str, episode_id: str):
        return evidence(store, analysis_id, episode_id)

    @app.post('/api/analyses/{analysis_id}/episodes/{episode_id}/explain')
    def explanation(analysis_id: str, episode_id: str, body: ExplainRequest):
        if body.audience not in {'analyst', 'viewer'} or body.provider not in {'local', 'foundry'}:
            raise ValueError('Choose an analyst/viewer audience and local/foundry provider')
        bundle = evidence(store, analysis_id, episode_id)
        if body.provider == 'foundry':
            return cloud.foundry_explain(bundle, body.audience, body.question)
        return explain(bundle, body.audience, body.question)

    @app.post('/api/analyses/{analysis_id}/reports')
    def report(analysis_id: str, body: ReportRequest, tasks: BackgroundTasks):
        jid = store.job('report')
        tasks.add_task(store.run, jid, build_report, store, analysis_id, body.episode_ids, body.notes, body.include_media)
        return {'job_id': jid}

    @app.get('/api/reports')
    def reports():
        return store.list('reports')

    @app.get('/api/reports/{report_id}/download')
    def report_download(report_id: str):
        store.read('reports', report_id)
        return FileResponse(store.path('reports', report_id) / 'report.zip', filename='movement-lens-report.zip', media_type='application/zip')

    @app.post('/api/reports/{report_id}/azure')
    def azure_save(report_id: str, tasks: BackgroundTasks):
        jid = store.job('azure')
        tasks.add_task(store.run, jid, cloud.save_report, store, report_id)
        return {'job_id': jid}

    @app.get('/api/reports/{report_id}/azure/download')
    def azure_download(report_id: str):
        return Response(cloud.download_report(store, report_id), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="movement-lens-azure-report.zip"'})

    @app.get('/api/azure/datasets')
    def azure_dataset_list(cursor: str | None = None):
        return azure_datasets.list_datasets(cursor)

    @app.post('/api/azure/datasets/import')
    def azure_dataset_import(body: AzureImportRequest, tasks: BackgroundTasks):
        jid = store.job('azure_dataset_import')
        tasks.add_task(store.run, jid, azure_datasets.import_snapshot, store, body.blob, body.sha256, body.etag)
        return {'job_id':jid}

    @app.post('/api/explorations')
    def exploration_create(body: ExplorationRequest, tasks: BackgroundTasks):
        jid = store.job('explore')
        tasks.add_task(store.run, jid, create_exploration, store, body.dataset_ids, body.reference_ids, body.clusters)
        return {'job_id':jid}

    @app.get('/api/explorations/{exploration_id}')
    def exploration_get(exploration_id: str):
        return public_exploration(store.read('explorations', exploration_id))

    @app.get('/api/explorations/{exploration_id}/examples')
    def exploration_examples(exploration_id: str, match_id: str):
        record = store.read('explorations', exploration_id)
        if match_id not in {m['id'] for m in record['matches']}:
            raise ValueError('Choose an available match')
        curated = status()['presentation'].get('curated_examples', [])
        return match_examples(record, match_id, curated if isinstance(curated,list) else [])

    @app.post('/api/explorations/{exploration_id}/search')
    def exploration_search(exploration_id: str, body: SearchRequest):
        return search(store.read('explorations', exploration_id), body.seed_key, body.radius, body.cross_match_only, body.same_match_only)

    @app.post('/api/explorations/{exploration_id}/regions')
    def exploration_regions(exploration_id: str, body: RegionRequest):
        return compare_regions(store.read('explorations', exploration_id), body.seed_key, body.comparison_key)

    @app.get('/api/research')
    def research():
        return {'papers':PAPERS, 'regions':[region_context(r) for r in REGIONS]}

    @app.post('/api/explorations/{exploration_id}/explain')
    def exploration_explain(exploration_id: str, body: PatternExplainRequest):
        facts = review_facts(store.read('explorations', exploration_id), body)
        return cloud.foundry_pattern_explain(facts, body.question) if body.provider == 'foundry' else local_pattern_explanation(facts)

    @app.post('/api/explorations/{exploration_id}/reviews')
    def review_create(exploration_id: str, body: ReviewRequest):
        return save_review(store, store.read('explorations', exploration_id), body)

    @app.post('/api/explorations/{exploration_id}/movement-explanation')
    def movement_explain(exploration_id: str, body: PatternExplainRequest):
        body = body.model_copy(update={'movement_only': True})
        record = store.read('explorations', exploration_id)
        facts = review_facts(record, body)
        result = cloud.foundry_pattern_explain(facts, body.question, movement_only=True) if body.provider == 'foundry' else local_movement_explanation(facts)
        return save_explanation(store, record, body, result)

    @app.get('/api/explorations/{exploration_id}/reviews')
    def review_list(exploration_id: str):
        store.read('explorations', exploration_id)
        return [{'id':r['id'], 'created':r['created'], 'seed_key':r['request']['seed_key'], 'status':r['facts']['context']['status']}
                for r in store.list('reviews') if r['exploration_id'] == exploration_id]

    @app.get('/api/reviews/{review_id}')
    def review_get(review_id: str):
        return store.read('reviews', review_id)

    @app.post('/api/reviews/{review_id}/reports')
    def review_report(review_id: str, body: SnapshotRequest, tasks: BackgroundTasks):
        store.read('reviews', review_id)
        jid = store.job('review_report')
        tasks.add_task(store.run, jid, build_review_report, store, review_id, body.include_media)
        return {'job_id':jid}

    frontend = Path(__file__).resolve().parents[1] / 'frontend/dist'
    if frontend.is_dir():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    else:
        @app.get('/')
        def frontend_missing():
            return {'message': 'Build the interface: cd frontend && npm ci && npm run build. Then restart the server.', 'docs': '/docs'}
    return app


app = create_app()
