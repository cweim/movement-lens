"""Proof of uncapped selection, safe reuse/resume and immutable activation."""
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from conftest import arrays, make_zip
from movement_lens.analysis import analyse
from movement_lens.importer import import_dataset
from movement_lens.store import sha_file

spec = importlib.util.spec_from_file_location('expand_local_library', Path(__file__).parents[1]/'scripts/expand_local_library.py')
expansion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(expansion)


def test_selects_all_nonoverlapping_candidates_without_a_demo_cap():
    windows = [dict(id=f'w{i}', tracklet_id='track', start=float(i), end=float(i+2)) for i in range(180)]
    selected = expansion.candidates(windows[::-1])
    assert len(selected) == 90
    assert [w['start'] for w in selected] == list(range(0, 180, 2))
    # Tracklet-relative sampling must not discard a separate track by accident.
    assert len(expansion.candidates(windows+[dict(id='other', tracklet_id='other', start=0., end=2.)])) == 91


def test_review_and_identity_exclusions_survive_export():
    row = dict(id='window', tracklet_id='track', shot_id='shot', start=0., end=2., flags=['imported_review_origin_unknown'])
    old = dict(flags=['identity_ambiguous'], review_source='visual_spot_check')
    exported = expansion.exported_row(row, 'match', 'model', old)
    assert exported['flags'] == ['identity_ambiguous', 'imported_review_origin_unknown']
    assert exported['review_source'] == 'visual_spot_check'
    fresh = expansion.exported_row(row, 'match', 'model')
    assert fresh['review_source'] == 'imported_unspecified'


def test_verified_pose_reuse_resume_and_corruption_detection(tmp_path, monkeypatch):
    state, output = tmp_path/'state', tmp_path/'checkpoints'
    parent = state/'datasets'/'existing'
    (parent/'arrays').mkdir(parents=True)
    (parent/'media').mkdir()
    np.savez_compressed(parent/'arrays/w_0.npz', **arrays())
    (parent/'media/w_0.mp4').write_bytes(b'controlled-video-fixture')
    model_tag = 'yolov8x-pose:384:fixture'
    row = dict(id='window', tracklet_id='track', shot_id='shot', start=0., end=2., flags=[])
    old = dict(row, id='w_0', original_id='window', source_hash='a'*64,
               pose_provenance='source_bound_recomputed', pose_model=model_tag,
               media='w_0.mp4', review_source='visual_spot_check', flags=['identity_ambiguous'])
    task = dict(old={'window': old}, job={'input_hash': 'a'*64}, dataset={'id': 'existing', 'match': 'match'})
    monkeypatch.setattr(expansion, 'copy_media', shutil.copyfile)

    def no_inference():
        pytest.fail('Verified reuse/resume must not invoke pose inference')

    result, origin = expansion.prepare_one(task, row, state, output, 'fingerprint', model_tag, no_inference, None)
    assert origin == 'reused_verified_dataset'
    assert result['quality']['usable'] is False  # exclusion was preserved
    assert result['row']['review_source'] == 'visual_spot_check'
    _, origin = expansion.prepare_one(task, row, state, output, 'fingerprint', model_tag, no_inference, None)
    assert origin == 'checkpoint'
    (output/'window.mp4').write_bytes(b'corrupted')
    assert not expansion.checkpoint_valid(result, 'fingerprint', output)
    repaired, origin = expansion.prepare_one(task, row, state, output, 'fingerprint', model_tag, no_inference, None)
    assert origin == 'reused_verified_dataset'
    assert expansion.checkpoint_valid(repaired, 'fingerprint', output)
    assert not expansion.checkpoint_valid(repaired, 'different-input', output)
    assert (parent/'media/w_0.mp4').read_bytes() == b'controlled-video-fixture'


def test_activation_preserves_old_snapshots_and_replaces_only_expanded_ids(store, cohort, tmp_path):
    ref, query, _ = cohort
    previous_analysis = analyse(store, query, [ref])['analysis_id']
    previous = dict(analysis_id=previous_analysis, query_id=query, reference_ids=[ref],
                    datasets=[dict(job_id='h1', dataset_id=ref), dict(job_id='e02', dataset_id=query)])
    expansion.atomic_json(store.root/'prepared/active-demo.json', previous)
    protected = {str(p): sha_file(p) for kind in ('datasets', 'analyses') for p in (store.root/kind).glob('*/record.json')}
    path = make_zip(tmp_path/'expanded.zip', match='reference', count=32)
    new = store.read('datasets', import_dataset(store, path, path.name)['dataset_id'])
    task = dict(job_id='h1', entry=dict(dataset_id=ref))
    updated = expansion.activate(store.root, previous, [(task, new)], store)
    assert updated['query_id'] == query
    assert updated['reference_ids'] == [new['id']]
    assert store.read('analyses', updated['analysis_id'])['reference_count'] == 32
    assert all(sha_file(Path(path)) == expected for path, expected in protected.items())
    assert json.loads((store.root/'prepared/active-demo.json').read_text()) == updated


def test_failed_analysis_does_not_activate_partial_expansion(store, cohort, monkeypatch):
    ref, query, _ = cohort
    previous = dict(analysis_id='previous', query_id=query, reference_ids=[ref], datasets=[])
    path = store.root/'prepared/active-demo.json'
    expansion.atomic_json(path, previous)
    before = path.read_bytes()

    def fail(*_):
        raise ValueError('insufficient reference variation')

    monkeypatch.setattr(expansion, 'analyse', fail)
    with pytest.raises(ValueError, match='variation'):
        expansion.activate(store.root, previous, [], store)
    assert path.read_bytes() == before


def test_activation_detects_a_changed_workspace(store):
    path = store.root/'prepared/active-demo.json'
    expansion.atomic_json(path, {'analysis_id': 'another-analysis'})
    before = path.read_bytes()
    with pytest.raises(ValueError, match='workspace changed'):
        expansion.activate(store.root, {'analysis_id': 'original-analysis'}, [], store)
    assert path.read_bytes() == before


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg is an optional local preparation prerequisite')
def test_new_window_encodes_bundles_and_imports_with_real_media(tmp_path, store, monkeypatch):
    pytest.importorskip('cv2')
    upstream = tmp_path/'touchline'
    upstream.mkdir()
    original = upstream/'window.npz'
    np.savez_compressed(original, **arrays())
    source = tmp_path/'source.fixture'
    source.write_bytes(b'controlled-test-source')
    row = dict(id='new-window', tracklet_id='track', shot_id='shot', start=0., end=2., flags=[],
               samples=50, sample_rate=25, array_path='window.npz')
    task = dict(job_id='fixture', label='fixture', old={}, touchline_runtime=upstream,
                dataset={'match': 'fixture'}, manifest={'signature': 'fixture'},
                job=dict(path=str(source), input_hash=sha_file(source), fps=25., width=1280, height=720,
                         duration=5., target='Test player'))
    frames = [np.full((512, 256, 3), i*4, dtype=np.uint8) for i in range(50)]
    calls = []

    def controlled_pose(model, cap, a, fps, device):
        calls.append(device)
        return a, frames

    monkeypatch.setattr(expansion, 'rebuild', controlled_pose)
    directory = tmp_path/'prepared'
    result, origin = expansion.prepare_one(task, row, store.root, directory, 'fixture-fingerprint',
                                            'yolov8x-pose:384:fixture', lambda: object(), None)
    assert origin == 'recomputed_exact_source' and calls == ['cpu']
    expansion.verify_media(directory/'new-window.mp4')
    bundle = expansion.package(task, [result], directory, 'b'*64, reference=False)
    upload = tmp_path/'import-copy.zip'
    shutil.copyfile(bundle, upload)
    record = store.read('datasets', import_dataset(store, upload, bundle.name)['dataset_id'])
    assert bundle.is_file()  # importer consumes only the temporary copy
    assert record['window_count'] == record['usable_count'] == record['media_count'] == 1
    assert record['windows'][0]['quality']['identity_provenance'] == 'imported_unspecified'
    assert record['windows'][0]['original_id'] == 'new-window'
    expansion.verify_media(store.path('datasets', record['id'])/'media'/record['windows'][0]['media'])


def test_drive_disconnect_does_not_cache_a_permanent_pose_rejection(tmp_path, store, monkeypatch):
    upstream = tmp_path/'touchline'
    upstream.mkdir()
    np.savez_compressed(upstream/'window.npz', **arrays())
    row = dict(id='window', tracklet_id='track', shot_id='shot', start=0., end=2., samples=50,
               sample_rate=25, array_path='window.npz', flags=[])
    task = dict(old={}, touchline_runtime=upstream, dataset={'match': 'fixture'},
                job={'path': str(tmp_path/'disconnected-source.mp4'), 'fps': 25., 'input_hash': 'a'*64})
    monkeypatch.setattr(expansion, 'rebuild', lambda *_: (None, []))
    output = tmp_path/'prepared'
    with pytest.raises(ValueError, match='drive disconnected'):
        expansion.prepare_one(task, row, store.root, output, 'fixture', 'model', lambda: object(), None)
    assert not (output/'window.json').exists()
