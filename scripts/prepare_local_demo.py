#!/usr/bin/env python3
"""Recompute selected local poses from exact source video; never modify Touchline.

This development helper needs OpenCV, Ultralytics, an existing checkpoint and
local Touchline caches. No downloads. Input is a JSON list of
{job_id, match}; jobs are read from the supplied research runtime, while cached
window arrays are read from the supplied Touchline runtime. Output is private.
Identity-review provenance remains unchanged; source binding is not identity proof.
"""
import argparse
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from movement_lens.features import JOINTS
from movement_lens.importer import import_dataset
from movement_lens.store import Store, digest, sha_file


def iou(a,b):
    x1,y1=np.maximum(a[:2],b[:2]);x2,y2=np.minimum(a[2:],b[2:])
    inter=max(0,x2-x1)*max(0,y2-y1)
    return inter/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter,1e-6)


def source_frame_bounds(start, fps):
    """Frame indices in [start, start + 2), tolerating timestamp roundoff."""
    return (int(math.ceil(start * fps - 1e-6)),
            int(math.ceil((start + 2) * fps - 1e-6)))


def rebuild(model, cap, a, fps, device):
    import cv2
    times=a['times'];boxes=a['bbox'];observed_times=a['source_times']
    n0,n1=source_frame_bounds(times[0],fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES,n0)
    frames={}
    for n in range(n0,n1):
        ok,frame=cap.read()
        if not ok:return None,[]
        frames[n]=frame
    crops=[];transforms=[]
    for t in observed_times:
        frame=frames.get(int(round(t*fps)))
        if frame is None:return None,[]
        idx=int(np.argmin(abs(times-t)));box=boxes[idx]
        x1,y1,x2,y2=box;w=x2-x1;h=y2-y1
        cx,cy=(x1+x2)/2,(y1+y2)/2
        left=max(0,int(cx-w*1.25));right=min(frame.shape[1],int(cx+w*1.25))
        top=max(0,int(cy-h*1.25));bottom=min(frame.shape[0],int(cy+h*1.25))
        if right-left<2 or bottom-top<2:return None,[]
        crop=frame[top:bottom,left:right];scale=384/crop.shape[0]
        crop=cv2.resize(crop,(max(1,round(crop.shape[1]*scale)),384))
        sx,sy=crop.shape[1]/(right-left),384/(bottom-top)
        crops.append(crop);transforms.append((left,top,sx,sy,box))
    keypoints=[];matched=[]
    for start in range(0,len(crops),8):
        preds=model(crops[start:start+8],device=device,imgsz=384,verbose=False,conf=.25)
        for pred,transform in zip(preds,transforms[start:start+8]):
            left,top,sx,sy,target=transform
            if pred.keypoints is None or len(pred.boxes)==0:return None,[]
            b=pred.boxes.xyxy.cpu().numpy().copy();b[:,[0,2]]=b[:,[0,2]]/sx+left;b[:,[1,3]]=b[:,[1,3]]/sy+top
            overlaps=[iou(target,x) for x in b];best=int(np.argmax(overlaps))
            if overlaps[best]<.15:return None,[]
            kp=pred.keypoints.data[best].cpu().numpy().copy();kp[:,0]=kp[:,0]/sx+left;kp[:,1]=kp[:,1]/sy+top
            keypoints.append(kp);matched.append(b[best])
    observed=np.array(keypoints);points=np.zeros((50,17,2),np.float32);conf=np.zeros((50,17),np.float32)
    for j in range(17):
        visible=observed[:,j,2]>=.3
        if visible.sum()<2:continue
        vt=observed_times[visible]
        inside=(times>=vt[0]-.08)&(times<=vt[-1]+.08)
        right=np.clip(np.searchsorted(vt,times),1,len(vt)-1)
        inside &= vt[right]-vt[right-1]<=.40001
        for axis in (0,1):points[:,j,axis]=np.interp(times,vt,observed[visible,j,axis])
        conf[:,j]=np.interp(times,observed_times,observed[:,j,2]);conf[~inside,j]=0;points[~inside,j]=0
    valid=conf>=.3
    length=(np.linalg.norm(points[:,5]-points[:,11],axis=1)+np.linalg.norm(points[:,6]-points[:,12],axis=1))/2
    body=valid[:,[5,6,11,12]].all(1)&(length>=5)
    valid &= body[:,None]
    normal=(points-(points[:,11]+points[:,12])[:,None,:]/2)/np.maximum(length[:,None,None],1)
    normal[~valid]=0
    updated=dict(times=times,keypoints=points,kp_x=points[:,:,0],kp_y=points[:,:,1],kp_conf=conf,bbox=boxes,
                 valid_mask=valid,normalised=normal,source_times=observed_times,observed_keypoints=observed,
                 observed_bbox=np.array(matched),source_frame_indices=np.rint(observed_times*fps).astype(np.int64),
                 interpolated=np.min(abs(times[:,None]-observed_times[None,:]),axis=1)>1e-5)
    video=[]
    for n,frame in frames.items():
        t=n/fps;idx=int(np.argmin(abs(times-t)));x1,y1,x2,y2=boxes[idx];w=x2-x1;h=y2-y1
        x1=max(0,int(x1-.125*w));x2=min(frame.shape[1],int(x2+.125*w));y1=max(0,int(y1-.125*h));y2=min(frame.shape[0],int(y2+.125*h))
        crop=frame[y1:y2,x1:x2]
        if not crop.size:return None,[]
        scale=min(256/crop.shape[1],512/crop.shape[0]);crop=cv2.resize(crop,(max(1,int(crop.shape[1]*scale)),max(1,int(crop.shape[0]*scale))))
        canvas=np.full((512,256,3),20,np.uint8);a0=(512-crop.shape[0])//2;b0=(256-crop.shape[1])//2
        canvas[a0:a0+crop.shape[0],b0:b0+crop.shape[1]]=crop;video.append(canvas)
    return updated,video


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--jobs',type=Path,required=True);parser.add_argument('--touchline-runtime',type=Path,required=True)
    parser.add_argument('--research-runtime',type=Path,required=True);parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--windows',type=int,default=24);parser.add_argument('--device',default='cpu');args=parser.parse_args()
    if args.device != 'cpu':
        raise ValueError('Use CPU for this verification helper: the installed YOLO pose version warns of an Apple MPS pose bug')
    if not args.checkpoint.is_file():raise ValueError('An existing local checkpoint is required; this script does not download models')
    store=Store();out=store.root/'prepared';out.mkdir(exist_ok=True);os.environ['YOLO_CONFIG_DIR']=str(store.root/'ultralytics')
    import cv2
    from ultralytics import YOLO
    model=YOLO(str(args.checkpoint));model_hash=sha_file(args.checkpoint)
    results=[]
    for task in json.loads(args.jobs.read_text()):
        jid=task['job_id'];directory=args.touchline_runtime/'jobs'/jid
        cached=json.loads((directory/'windows/manifest.json').read_text())
        job=json.loads((args.research_runtime/'jobs'/jid/'run_config.json').read_text())
        source=Path(job['path'])
        print(f'Checking exact source hash: {task["match"]}',flush=True)
        if sha_file(source)!=job['input_hash']:raise ValueError('Source video hash does not match its recorded job')
        # Prefer complete windows; use different tracklets spread across the source.
        candidates=[];seen=set()
        ordered=sorted(cached['windows'],key=lambda w:(-w.get('pose_quality',0),w['start']))
        for w in ordered:
            if w['tracklet_id'] not in seen:
                candidates.append(w);seen.add(w['tracklet_id'])
        indices=np.linspace(0,len(candidates)-1,min(args.windows,len(candidates)),dtype=int)
        chosen=[candidates[i] for i in indices]
        rows=[];tracks=[];path=out/f'{jid}-source-bound.zip';cap=cv2.VideoCapture(str(source))
        try:
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
                for index,w in enumerate(chosen):
                    with np.load(args.touchline_runtime/w['array_path'],allow_pickle=False) as f:a={k:f[k] for k in f.files}
                    updated,video=rebuild(model,cap,a,job['fps'],args.device)
                    print(f'{jid}: recomputed {index+1}/{len(chosen)}'+(' — no matched pose' if updated is None else ''),flush=True)
                    if updated is None:continue
                    wid=w['id'];temp=out/f'{wid}.raw.mp4';encoded=out/f'{wid}.mp4'
                    writer=cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*'mp4v'),job['fps'],(256,512))
                    for frame in video:writer.write(frame)
                    writer.release()
                    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(temp),'-c:v','libx264','-preset','veryfast','-crf','21','-an',str(encoded)],check=True)
                    row={k:v for k,v in w.items() if k not in {'array_path','representative'}}
                    row.update(array=f'windows/{wid}.npz',video=f'windows/{wid}.mp4',pose_provenance='source_bound_recomputed',
                               pose_model='yolov8x-pose:384:'+model_hash[:16],match=task['match'])
                    payload=io.BytesIO();np.savez_compressed(payload,**updated);z.writestr(row['array'],payload.getvalue());z.write(encoded,row['video'])
                    temp.unlink();encoded.unlink();rows.append(row);tracks.append({'tracklet_id':row['tracklet_id'],'start':row['start'],'end':row['end']})
                manifest=dict(schema_version=1,created=time.time(),mode='windows',job_id=jid,match=task['match'],target_player=job['target'],
                              timestamp_basis='original_source_seconds',intervals='[start,end)',keypoint_order=JOINTS,
                              source={k:job[k] for k in ('width','height','fps','duration')}|{'sha256':job['input_hash'],'filename':source.name},
                              models={'pose_sha256':model_hash},snapshot_signature=digest([job['input_hash'],model_hash,[r['id'] for r in rows]]),
                              window_build_signature=cached['signature'],window_count=len(rows),tracklet_count=len(tracks),included_video=True)
                z.writestr('manifest.json',json.dumps(manifest));z.writestr('windows.json',json.dumps(rows));z.writestr('tracklets.json',json.dumps(tracks))
        finally:cap.release()
        # Retain the prepared ZIP and import a separate temporary copy.
        copy=out/f'{jid}-import.zip';copy.write_bytes(path.read_bytes())
        result=import_dataset(store,copy,path.name);record=store.read('datasets',result['dataset_id'])
        results.append({'job_id':jid,'dataset_id':record['id'],'windows':record['window_count'],'usable':record['usable_count']})
        print('Imported:',results[-1],flush=True)
    (out/'prepared.json').write_text(json.dumps(results,indent=2));print(json.dumps(results),flush=True)


if __name__=='__main__':main()
