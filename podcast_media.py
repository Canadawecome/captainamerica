"""Media utilities: FFprobe, SHA256, sparse actual-frame evidence, audio flag."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path


def digest(file:Path):
    h=hashlib.sha256()
    with Path(file).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def probe(file:Path):
    p=subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(file)],capture_output=True,text=True)
    if p.returncode:raise ValueError('FFPROBE_FAILED: '+p.stderr[-200:])
    data=json.loads(p.stdout)
    v=next((s for s in data['streams'] if s['codec_type']=='video'),None)
    a=next((s for s in data['streams'] if s['codec_type']=='audio'),None)
    if not v:raise ValueError('NO_VIDEO_STREAM')
    return {'duration':float(data['format']['duration']),'width':int(v['width']),'height':int(v['height']),
            'has_audio':a is not None,'audio_codec':a.get('codec_name') if a else None}

def evidence(file:Path, output:Path, interval:float=5,limit:int=60):
    info=probe(file)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if interval<.5:raise ValueError('interval must be >=0.5')
    import math
    n=min(limit,max(2,int(math.ceil(info['duration']/interval))))
    times=[round(min(info['duration']-.3, i*(info['duration']-.3)/(n-1)),3) for i in range(n)]
    frames=[]
    for i,t in enumerate(times):
        pic=output/f'frame_{i:04d}.jpg'
        p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(file),'-frames:v','1','-vf','scale=480:-2','-q:v','5',str(pic)],capture_output=True)
        if p.returncode or not pic.exists():raise ValueError('Unable to extract video evidence')
        frames.append({'id':f'frame_{i:04d}','seconds':t,'path':pic.name})
    result={'schema_version':'podcast-v1','media_sha256':digest(file),'duration':info['duration'],
            'frames':frames,'note':'Sampled stills only; transcript supplies speech and timing, audio needs separate QC.'}
    (output/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
