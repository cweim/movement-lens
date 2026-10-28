"""Controlled geometry fixtures; never shipped as real football data."""
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from movement_lens.features import JOINTS
from movement_lens.importer import import_dataset
from movement_lens.store import Store


def arrays(start=0, variant=0):
    t=np.arange(50)/25
    phase=t*5+variant*.13
    amp=9+variant*.6
    p=np.zeros((50,17,2),dtype=np.float32)
    p[:]=[300,200]
    p[:,5]=np.stack([286+np.sin(phase)*2,np.full(50,210)],axis=1)
    p[:,6]=np.stack([314+np.sin(phase)*2,np.full(50,210)],axis=1)
    p[:,11]=[292,260];p[:,12]=[308,260]
    p[:,13]=np.stack([292+np.sin(phase)*amp,np.full(50,300)],axis=1)
    p[:,14]=np.stack([308-np.sin(phase)*amp,np.full(50,300)],axis=1)
    p[:,15]=np.stack([292-np.sin(phase)*amp,np.full(50,340)],axis=1)
    p[:,16]=np.stack([308+np.sin(phase)*amp,np.full(50,340)],axis=1)
    conf=np.full((50,17),.95,dtype=np.float32)
    observed=np.concatenate([p[::2],conf[::2,:,None]],axis=2)
    bbox=np.tile([260,180,345,355],(50,1)).astype(np.float32)
    times=t+start
    return dict(times=times,keypoints=p,kp_conf=conf,bbox=bbox,valid_mask=np.ones((50,17),dtype=bool),
                source_times=times[::2],observed_keypoints=observed,observed_bbox=bbox[::2],
                source_frame_indices=np.rint(times[::2]*25).astype(np.int64),interpolated=np.arange(50)%2==1)


def make_zip(path, match='reference', count=24, offset=0, provenance='source_bound', mutate=None, media=False):
    windows=[];tracks=[]
    for i in range(count):
        tid=f'{match}-track-{i//2}'
        if i%2==0:tracks.append({'tracklet_id':tid})
        windows.append(dict(id=f'{match}-window-{i}',tracklet_id=tid,shot_id=f's{i//2}',start=float(i*3),end=float(i*3+2),samples=50,sample_rate=25,
                            array=f'windows/{i}.npz',video=f'windows/{i}.mp4' if media else None,
                            review_source='human',pose_provenance=provenance,pose_model='test-geometry'))
    manifest=dict(schema_version=1,keypoint_order=JOINTS,timestamp_basis='original_source_seconds',intervals='[start,end)',
                  match=match,target_player='Test player',source=dict(sha256=hashlib.sha256(match.encode()).hexdigest(),width=1280,height=720,fps=25),
                  window_count=count,tracklet_count=len(tracks),snapshot_signature='test-snapshot')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest));z.writestr('windows.json',json.dumps(windows));z.writestr('tracklets.json',json.dumps(tracks))
        for i,row in enumerate(windows):
            a=arrays(row['start'],i+offset)
            if mutate:mutate(a,i)
            data=io.BytesIO();np.savez_compressed(data,**a);z.writestr(row['array'],data.getvalue())
            if media:z.writestr(row['video'],b'test-video-payload')
    return path


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'state')


@pytest.fixture
def cohort(store,tmp_path):
    ids=[]
    for name,n,offset in [('reference',24,0),('query',12,15),('calibration',32,2)]:
        p=make_zip(tmp_path/f'{name}.zip',name,n,offset)
        ids.append(import_dataset(store,p,p.name)['dataset_id'])
    return ids
