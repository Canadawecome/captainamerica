#!/usr/bin/env python3
"""Deterministic local recut from original footage (not already re-ordered Opus result).

Native source-to-clip mapping remains explicit and unapproved. Use source video only
with verified usage rights; all recuts require new ASR/evidence/GPT review and hash seals.
"""
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
from opus_expert_core import sha256

MAX_ATTEMPTS=2

def proposal(source_interval,reason:str,attempt:int=1,pad_start:float=3,pad_end:float=5,source_total:float|None=None):
    if attempt<1 or attempt>MAX_ATTEMPTS:raise ValueError('RECUT_LIMIT_EXCEEDED')
    a,b=map(float,source_interval)
    a=max(0.,a-pad_start);b=b+pad_end
    if source_total is not None:b=min(float(source_total),b)
    if b-a<=65.:raise ValueError('RECUT_TOO_SHORT')
    return {'schema_version':'opus-expert-recut-v1','source_start_sec':a,'source_end_sec':b,
            'reason':reason,'attempt':attempt,'status':'NEEDS_EDITOR_OR_GPT_SOURCE_BOUNDARY_APPROVAL',
            'safe_to_publish':False,'rights_recheck_required':True}

def render(source:Path,recut_plan:dict,out:Path,*,approved_boundary:bool=False):
    if not approved_boundary:raise ValueError('RECUT_NEEDS_BOUNDARY_APPROVAL')
    if recut_plan['status']!='NEEDS_EDITOR_OR_GPT_SOURCE_BOUNDARY_APPROVAL':raise ValueError('Invalid recut plan')
    source=source.resolve();out=out.resolve()
    if out.exists():raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    a,b=recut_plan['source_start_sec'],recut_plan['source_end_sec']
    # Re-encode to ensure 9:16 and clean timestamps, preserving the ORIGINAL spoken
    # audio for podcast or raw ASMR for craft; ASMR narration handled downstream.
    vf='scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1'
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-ss',str(a),'-i',str(source),
         '-t',str(b-a),'-map','0:v:0','-map','0:a:0','-vf',vf,'-c:v','libx264','-preset','veryfast',
         '-crf','21','-c:a','aac','-b:a','160k','-movflags','+faststart',str(out)]
    proc=subprocess.run(cmd,capture_output=True,text=True)
    if proc.returncode or not out.exists():raise RuntimeError('RECUT_FFMPEG_FAILED: '+proc.stderr[-1000:])
    manifest={'recut_from_source_sha256':sha256(source),'clip_sha256':sha256(out),
              'source_window':[a,b],'attempt':recut_plan['attempt'],
              'status':'UNREVIEWED_REQUIRES_FRESH_GPT_ASR_AND_APPROVAL'}
    (out.with_suffix('.recut.json')).write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--approved-boundary',action='store_true')
    x=p.parse_args();print(json.dumps(render(x.source,json.loads(x.plan.read_text()),x.output,approved_boundary=x.approved_boundary),indent=2))
if __name__=='__main__':main()
