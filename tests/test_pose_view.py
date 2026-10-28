"""Display framing must follow the clip, preserve gaps and leave metrics alone."""
import numpy as np
from fastapi.testclient import TestClient

from movement_lens.app import create_app
from movement_lens.pose_view import player_pose
from movement_lens.store import sha_file


def test_pose_uses_player_crop_scale_and_letterbox_not_svg_autofit():
    points = np.array([[[150., 200.], [100., 100.], [200., 300.]]])
    boxes = np.array([[100., 100., 200., 300.]])
    saved = points.copy()
    result = player_pose(points, boxes, np.array([[True, True, False]]), 1280, 720)
    assert result['view_box'] == [0, 0, 256, 512]
    assert result['frames'][0][0] == [129.024, 256.0]
    assert result['frames'][0][1] == [26.624, 51.2]
    assert result['frames'][0][2] is None
    np.testing.assert_array_equal(points, saved)


def test_pose_tracks_zoom_and_source_boundaries():
    points = np.array([[[150., 200.]], [[300., 400.]]])
    boxes = np.array([[100., 100., 200., 300.], [200., 200., 400., 600.]])
    result = player_pose(points, boxes, np.ones((2, 1), dtype=bool), 1280, 720)
    np.testing.assert_allclose(result['frames'][0], result['frames'][1], atol=1.1)
    edge = player_pose(np.array([[[0., 50.]]]), np.array([[0., 50., 100., 250.]]), np.ones((1, 1), dtype=bool), 1280, 720)
    assert edge['frames'][0][0] == [13., 51.2]


def test_invalid_player_box_remains_a_gap():
    result = player_pose(np.zeros((1, 17, 2)), np.array([[100., 100., 100., 300.]]), np.ones((1, 17), dtype=bool), 1280, 720)
    assert result['frames'] == [[None]*17]


def test_api_adds_display_pose_without_changing_features_or_artifacts(store, cohort):
    _, query, _ = cohort
    before = store.read('datasets', query)
    path = store.path('datasets', query)/'arrays/w_00000.npz'
    original_hash = sha_file(path)
    client = TestClient(create_app(store.root))
    response = client.get(f'/api/datasets/{query}/windows/w_00000')
    assert response.status_code == 200
    window = response.json()
    assert len(window['skeleton']) == len(window['pose_view']['frames']) == 50
    assert window['pose_view']['basis'] == 'tracked_player_crop'
    assert window['features'] == before['windows'][0]['features']
    assert sha_file(path) == original_hash
    assert store.read('datasets', query) == before
