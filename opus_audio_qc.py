#!/usr/bin/env python3
"""Offline audio diagnostics; numeric flags are NOT listening or speech verification.

Use on native-English podcast or ASMR output. Never makes speech correctness claims.
"""
import argparse,json,re,subprocess
from pathlib import Path

def audio_report(media:Path)->dict:
    p=Path(media)
    if not p.is_file():raise FileNotFoundError(p)
    probe=subprocess.run(['ffprobe','-v','error','-of','json','-show_streams','-show_format',str(p)],capture_output=True,text=True)
    if probe.returncode:raise ValueError('FFPROBE_FAILED')
    d=json.loads(probe.stdout);streams=[s for s in d.get('streams',[]) if s.get('codec_type')=='audio']
    if not streams:raise ValueError('AUDIO_STREAM_MISSING')
    cmd=['ffmpeg','-hide_banner','-nostdin','-i',str(p),'-vn',
         '-af','silencedetect=noise=-40dB:d=0.7,astats=metadata=0:reset=0',
         '-f','null','-']
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode:raise ValueError('AUDIO_QC_FFMPEG_FAILED')
    intervals=[];starts=[]
    for line in r.stderr.splitlines():
        m=re.search(r'silence_start:\s*([0-9.]+)',line)
        if m:starts.append(float(m.group(1)))
        m=re.search(r'silence_end:\s*([0-9.]+)',line)
        if m and starts:intervals.append([starts.pop(0),float(m.group(1))])
    duration=float(d.get('format',{}).get('duration',0) or 0)
    for a in starts:intervals.append([a,duration])
    rms_matches=re.findall(r'RMS level dB:\s*([-0-9.inf]+)',r.stderr)
    peak_matches=re.findall(r'Peak level dB:\s*([-0-9.inf]+)',r.stderr)
    silenced=sum(max(0,b-a) for a,b in intervals)
    return {'file':str(p),'duration_sec':duration,'has_audio':True,
            'audio_codec':streams[0].get('codec_name'),'channels':streams[0].get('channels'),
            'rms_dbfs':rms_matches[-1] if rms_matches else None,
            'peak_dbfs':peak_matches[-1] if peak_matches else None,
            'silence_intervals_40db':intervals,
            'silence_ratio':round(silenced/duration,4) if duration>0 else None,
            'warnings':(['EXTENDED_SILENCE'] if silenced>duration*.35 else []),
            'requires_human_listening_for_speech_accuracy':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--media',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audio_report(a.media);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2),encoding='utf8');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
