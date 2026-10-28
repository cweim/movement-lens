import {useEffect,useMemo,useRef,useState} from 'react';
import {Eye,Loader2} from 'lucide-react';

type Quality = {usable:boolean; status:string; reasons:string[]; source_observations:number; interpolated_fraction:number; joint_valid_fraction:number; identity_provenance:string; source_binding:string};
export type WindowRecord = {id:string; original_id:string; dataset_id:string; tracklet_id:string; start:number; end:number; media:string|null; quality:Quality; traces:Record<string,(number|null)[]>; features:Record<string,number>; skeleton?:([number,number]|null)[][]; pose_view?:{frames:([number,number]|null)[][];view_box:number[];basis:string;label:string}; bones?:number[][]; video_url?:string|null};
export type Dataset = {id:string; match:string; player:string; filename:string; created:number; window_count:number; usable_count:number; media_count:number; archive_sha256:string; source:{sha256:string; fps:number}; coverage:{observed_seconds:number; usable_seconds:number; source_duration:number|null; fraction:number|null; intervals:number[][]}; windows?:WindowRecord[]};

function Skeleton({w,frame}:{w:WindowRecord; frame:number}) {
  const bounds = useMemo(()=>{
    if(w.pose_view) return w.pose_view.view_box;
    const p=(w.skeleton||[]).flat().filter((x):x is [number,number]=>x!==null);
    if(!p.length) return [-2,-2,4,5];
    const xs=p.map(x=>x[0]),ys=p.map(x=>x[1]);
    const x=Math.min(...xs),y=Math.min(...ys),width=Math.max(.5,Math.max(...xs)-x),height=Math.max(.5,Math.max(...ys)-y);
    return [x-width*.18,y-height*.12,width*1.36,height*1.24];
  },[w.id,w.skeleton,w.pose_view]);
  const p=(w.pose_view?.frames||w.skeleton)?.[frame];
  return <svg className="skeleton" viewBox={bounds.join(' ')} preserveAspectRatio="xMidYMid meet" role="img" aria-label={w.pose_view?'Standalone player-scaled pose at current relative time':'Standalone hip-centred pose at current relative time'}>{p && <g>
    {(w.bones||[]).map(([a,b],i)=>p[a]&&p[b]?<line key={i} x1={p[a]![0]} y1={p[a]![1]} x2={p[b]![0]} y2={p[b]![1]} stroke={a%2?'#236e55':'#879d8c'} strokeWidth={bounds[2]*.017} strokeLinecap="round"/>:null)}
    {p.map((v,i)=>v?<circle key={i} cx={v[0]} cy={v[1]} r={bounds[2]*.025} fill={i>=11?'#236e55':'#97b79e'} stroke="#fff" strokeWidth={bounds[2]*.007}/>:null)}
  </g>}</svg>;
}

export function Clip({w,clock,playing,rate,role,title}:{w:WindowRecord|null;clock:number;playing:boolean;rate:number;role:string;title:string}) {
  const video=useRef<HTMLVideoElement>(null);
  useEffect(()=>{ const el=video.current;if(!el)return;el.playbackRate=rate;if(playing)el.play().catch(()=>{});else el.pause(); },[playing,rate,w?.video_url]);
  const seek=()=>{const el=video.current;if(el)el.currentTime=Math.min(clock,Number.isFinite(el.duration)?Math.max(0,el.duration-.01):clock);};
  useEffect(()=>{ const el=video.current;if(el && (!playing || Math.abs(el.currentTime-clock)>.08))seek(); },[clock,playing,w?.video_url]);
  return <div className="clip-card"><div className="clip-heading"><span className={'tag '+(role==='QUERY'?'green':'')}>{role}</span><span className="muted small">{w?`${w.start.toFixed(2)}–${w.end.toFixed(2)}s`:'Loading…'}</span></div><h3 title={title}>{title}</h3>
    <div className="clip-visual"><div className="video-well">{w?.video_url?<video ref={video} src={w.video_url} onLoadedMetadata={seek} loop muted playsInline preload="auto" aria-label={`${role.toLowerCase()} source clip`}/>:<div className="missing-media"><Eye size={26}/><span>No video in export</span><small>Pose view remains available</small></div>}</div>
    <div className="pose-well"><span className="tiny-label">{w?.pose_view?'PLAYER-SCALED POSE':'POSE VIEW'}</span>{w?.skeleton?<Skeleton w={w} frame={Math.min(49,Math.floor(clock*25))}/>:<Loader2 className="spin" size={20}/>}<span className="tiny-label">{Math.min(50,Math.floor(clock*25)+1)} / 50 samples</span></div></div>
    <div className="clip-footer"><span className={'dot-label '+(w?.quality.usable?'ok':'warn')}>{w?.quality.usable?'Passes pose checks':'Limited evidence'}</span><span className="muted small">{w?.quality.source_observations||'—'} observations</span></div><div className="identity-line">{w?.quality.identity_provenance==='visual_spot_check'?'Player identity spot-checked':w?.quality.identity_provenance==='imported_unspecified'?'Player identity not independently checked':'Identity review: '+(w?.quality.identity_provenance?.replaceAll('_',' ')||'not provided')}</div>
  </div>;
}

export function Traces({query,reference,clock}:{query:WindowRecord|null; reference:WindowRecord|null; clock:number}) {
  const [joint,setJoint]=useState('left_knee');
  const a=query?.traces[joint]||[],b=reference?.traces[joint]||[];
  const values=[...a,...b].filter((v):v is number=>v!==null);
  const lo=values.length?Math.floor(Math.min(...values)/10)*10:0,hi=values.length?Math.ceil(Math.max(...values)/10)*10+1:180;
  const path=(v:(number|null)[])=>{let d='',open=false;v.forEach((y,i)=>{if(y===null){open=false;return;}d+=`${open?'L':'M'}${40+i/49*670},${135-(y-lo)/Math.max(hi-lo,1)*110} `;open=true;});return d;};
  return <div className="panel trace-panel"><div className="split"><h3>Movement trace</h3><select aria-label="Descriptor trace" value={joint} onChange={e=>setJoint(e.target.value)}>{['left_knee','right_knee','left_hip','right_hip'].map(v=><option key={v} value={v}>{v.replace('_',' ')} · projected angle</option>)}</select></div>
    <svg viewBox="0 0 740 170" role="img" aria-label="Query and reference projected angle traces sharing the same scale">{[0,.5,1].map(v=><g key={v}><line x1="40" x2="710" y1={25+v*110} y2={25+v*110} stroke="#e7ece6"/><text x="30" y={29+v*110} textAnchor="end" fill="#829185" fontSize="10">{Math.round(hi-v*(hi-lo))}°</text></g>)}<path d={path(b)} fill="none" stroke="#a8b99f" strokeWidth="2"/><path d={path(a)} fill="none" stroke="#216f55" strokeWidth="2.5"/><line x1={40+clock/1.96*670} x2={40+clock/1.96*670} y1="20" y2="140" stroke="#c9893f" strokeDasharray="3 4"/>{[0,1,1.96].map(t=><text key={t} x={40+t/1.96*670} y="159" fill="#829185" fontSize="10" textAnchor="middle">{t}s</text>)}</svg>
    <div className="trace-legend"><span><i/>Query</span><span><i/>Reference</span><small>Shared scale · gaps stay missing · relative-time playback</small></div></div>;
}

