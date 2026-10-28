#!/usr/bin/env python3
"""Recompute a compact legacy Touchline export against its exact original video."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from movement_lens.importer import archive_entries, read_json, load_arrays
from movement_lens.store import sha_file, digest
from prepare_local_demo import rebuild


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=24);args=p.parse_args()
    if not 1<=args.limit<=100:raise ValueError('Choose a compact verification batch between one and 100 windows')
    if args.output.exists() or args.output.resolve()==args.dataset.resolve():raise ValueError('Choose a new output file; original exports are never overwritten')
    if not args.checkpoint.is_file() or not args.source.is_file():raise ValueError('The exact source and existing local checkpoint must be available')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.dataset) as src:
        archive_entries(src);manifest=read_json(src,'manifest.json');windows=read_json(src,'windows.json');tracks=read_json(src,'tracklets.json')
        print('Verifying full source SHA-256…',flush=True)
        if sha_file(args.source)!=manifest['source']['sha256']:raise ValueError('Selected video does not match the export source hash')
        selected=[];seen=set()
        for row in windows:
            if row['tracklet_id'] in seen:continue
            selected.append(row);seen.add(row['tracklet_id'])
        indices=__import__('numpy').linspace(0,len(selected)-1,min(args.limit,len(selected)),dtype=int)
        selected=[selected[i] for i in indices]
        with tempfile.TemporaryDirectory(dir=args.output.parent) as temp:
            temp=Path(temp);os.environ['YOLO_CONFIG_DIR']=str(temp/'ultralytics')
            import cv2
            import numpy as np
            from ultralytics import YOLO
            model=YOLO(str(args.checkpoint));model_hash=sha_file(args.checkpoint)
            cap=cv2.VideoCapture(str(args.source));rows=[]
            partial=args.output.with_suffix('.partial')
            try:
                with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED) as dest:
                    for i,row in enumerate(selected):
                        arrays=load_arrays(src.read(row['array']),row)
                        updated,frames=rebuild(model,cap,arrays,manifest['source']['fps'],'cpu')
                        print(f'Verifying {i+1}/{len(selected)}'+(' · no matched pose' if updated is None else ''),flush=True)
                        if updated is None:continue
                        local_id=f'verified-{i:04d}';raw=temp/f'{local_id}.raw.mp4';mp4=temp/f'{local_id}.mp4'
                        writer=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*'mp4v'),manifest['source']['fps'],(256,512))
                        for frame in frames:writer.write(frame)
                        writer.release()
                        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(raw),'-c:v','libx264','-preset','veryfast','-crf','21','-an',str(mp4)],check=True)
                        new=row|{'array':f'windows/{local_id}.npz','video':f'windows/{local_id}.mp4','pose_provenance':'source_bound_recomputed',
                                 'pose_model':'yolov8x-pose:384:'+model_hash[:16], 'context_video':None,'context_start':None,'context_end':None}
                        data=io.BytesIO();np.savez_compressed(data,**updated);dest.writestr(new['array'],data.getvalue());dest.write(mp4,new['video']);rows.append(new)
                    if not rows:raise ValueError('No windows could be recomputed from the selected source')
                    selected_tracks=[t for t in tracks if t['tracklet_id'] in {r['tracklet_id'] for r in rows}]
                    new_manifest=manifest|{'created':time.time(),'window_count':len(rows),'tracklet_count':len(selected_tracks),'included_video':True,
                                           'snapshot_signature':digest([manifest['snapshot_signature'],model_hash,[r['id'] for r in rows]]),
                                           'verification':{'source_hash_checked':True,'pose_device':'cpu','pose_model_sha256':model_hash,
                                                           'identity_review':'Preserved from upstream; source binding does not verify identity'}}
                    dest.writestr('manifest.json',json.dumps(new_manifest));dest.writestr('windows.json',json.dumps(rows));dest.writestr('tracklets.json',json.dumps(selected_tracks))
                partial.replace(args.output)
            finally:
                cap.release();partial.unlink(missing_ok=True)
    print('Prepared source-bound export:',args.output,flush=True)


if __name__=='__main__':main()
