#!/usr/bin/env python3
"""Native-audio podcast renderer: original spoken voices + real word-aligned captions.

No TTS. No speech removal. No voice replacement. No source-narration script.
"""
from __future__ import annotations
import argparse,json,re,subprocess
from pathlib import Path
from podcast_director import require_approved,transcript,semantic_boundaries
from podcast_media import probe,digest


def ts(seconds:float,ass=False)->str:
    n=int(round(seconds*(100 if ass else 1000)))
    if ass:
        h,n=divmod(n,360000);m,n=divmod(n,6000);s,c=divmod(n,100)
        return f'{h}:{m:02}:{s:02}.{c:02}'
    h,n=divmod(n,3600000);m,n=divmod(n,60000);s,ms=divmod(n,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def cues(words,max_words=4):
    """Only use measured ASR/provider word times. Never interpolate word timings."""
    groups=[];block=[]
    for w in words:
        if block and (len(block)>=max_words or w.start-block[-1].end>.48 or w.speaker!=block[-1].speaker):
            groups.append(block);block=[]
        block.append(w)
        if w.text.rstrip().endswith(('.', '?', '!')):
            groups.append(block);block=[]
    if block:groups.append(block)
    return [{'start':c[0].start,'end':c[-1].end,'speaker':c[0].speaker,
             'text':' '.join(w.text.strip() for w in c)} for c in groups]


def subtitles(folder:Path,sub_height_ratio=.85):
    clip=folder/'clip.mp4'; tx=transcript(folder/'clip_transcript.json',clip)
    info=probe(clip)
    cs=cues(tx.words)
    if not cs:raise ValueError('EMPTY_CAPTIONS')
    srt='\n'.join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n" for i,c in enumerate(cs,1))
    (folder/'captions_en.srt').write_text(srt,encoding='utf8')
    width,height=info['width'],info['height'];fontsize=max(12,round(width*.05));y=round(height*sub_height_ratio)
    header=(f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n'
           '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, '
           'OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, '
           'Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
           f'Style: Default,Inter,{fontsize},&H00FFFFFF,&H0000DEFF,&H00000000,&H80000000,'
           '1,0,0,0,100,100,0,0,1,2.5,0.5,5,15,15,0,1\n'
           '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    dialogs=[]
    for c in cs:
        clean=c['text'].replace('\\','').replace('{','(').replace('}',')').replace('\n',' ')
        dialogs.append(f"Dialogue: 0,{ts(c['start'],True)},{ts(c['end'],True)},Default,,0,0,0,,{{\\pos({width//2},{y})}}{clean}")
    assfile=folder/'captions_en.ass'
    assfile.write_text(header+'\n'.join(dialogs)+'\n',encoding='utf8')
    return cs


def render(folder:Path,audio_mode='preserve'):
    folder=Path(folder).resolve()
    require_approved(folder)
    video=folder/'clip.mp4'
    info=probe(video)
    if not info['has_audio']:raise ValueError('NO_NATIVE_VOICE_AUDIO')
    if info['duration']<=65.:raise ValueError('DURATION_NOT_ABOVE_65')
    tx=transcript(folder/'clip_transcript.json',video)
    quality=semantic_boundaries(tx,info['duration'])
    # Punctuation from ASR is not proof that a spoken sentence was truncated.
    # The signed semantic reviewer decision is the authoritative gate.
    cs=subtitles(folder)
    out=folder/'final.mp4';temp=folder/'final.partial.mp4'
    temp.unlink(missing_ok=True)
    # Quotes and colons within user paths need escaping by libavfilter.
    ass_path=str((folder/'captions_en.ass').resolve()).replace('\\','\\\\').replace(':','\\:').replace("'","\\'").replace(',','\\,')
    vf=f"ass='{ass_path}'"
    if audio_mode=='preserve':audio=['-c:a','copy'] if info['audio_codec']=='aac' else ['-c:a','aac','-b:a','160k']
    elif audio_mode=='dialogue_mild':audio=['-c:a','aac','-b:a','160k','-af','highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11']
    else:raise ValueError('Unknown audio preset')
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(video),
         '-map','0:v:0','-map','0:a:0','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','20',
         *audio,'-movflags','+faststart',str(temp)]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True)
        if p.returncode:raise RuntimeError('FFMPEG_RENDER_FAILED: '+p.stderr[-1500:])
        actual=probe(temp)
        if not actual['has_audio']:raise ValueError('FINAL_DROPPED_ORIGINAL_AUDIO')
        if abs(actual['duration']-info['duration'])>.28:raise ValueError('FINAL_DURATION_MISMATCH')
        temp.replace(out)
        report={'status':'PASS_NATIVE_PODCAST_AUDIO','source_clip_sha256':digest(video),
                'original_dialogue_kept':True,'audio_stream_copied':audio_mode=='preserve' and info['audio_codec']=='aac',
                'elevenlabs_used':False,'asr_words':len(tx.words),
                'captions':len(cs),'duration_sec':actual['duration'],'audio_mode':audio_mode,
                'subtitle_size_px':round(info['width']*.05),'subtitle_vertical_pct':85,
                'notes':'Aural listening check still needed to verify real sound quality.'}
        (folder/'qc_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        return report
    finally:temp.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--audio',choices=['preserve','dialogue_mild'],default='preserve');a=p.parse_args()
    print(json.dumps(render(a.folder,a.audio),indent=2))
if __name__=='__main__':main()
