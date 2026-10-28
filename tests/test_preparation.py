import importlib.util
from pathlib import Path

import numpy as np
import pytest


spec = importlib.util.spec_from_file_location(
    'local_pose_preparation', Path(__file__).resolve().parents[1] / 'scripts/prepare_local_demo.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


@pytest.mark.parametrize('start,fps', [
    (0.,25), (.01,25), (1296.4,25), (2187.76,25), (100.123,29.97),
])
def test_source_clip_frames_stay_inside_the_half_open_window(start,fps):
    first,end=preparation.source_frame_bounds(start,fps)
    times=np.arange(first,end)/fps
    assert np.all(times >= start-1e-7)
    assert np.all(times < start+2-1e-7)
    assert (first-1)/fps < start-1e-7
    assert end/fps >= start+2-1e-7
    if fps==25:
        assert len(times)==50
