"""Import word timestamps from ASR/provider JSON or optional local faster-whisper.

Never invent word timestamps by linearly interpolating a plain transcript.
Speaker identity is 'unknown' unless reliable diarization is supplied.
"""
from __future__ import annotations
import argparse,json,subprocess,tempfile
from pathlib import Path
from podcast_contracts import Transcript
from podcast_media import digest,probe


def from_words(media:Path,word_rows:list[dict],source='PROVIDER_ALIGNED_WORDS')->Transcript:
    actual=probe(media)
    if not actual['has_audio']:raise ValueError('SOURCE_HAS_NO_AUDIO: cannot subtitle an English podcast')
    t=Transcript.model_validate({'media_sha256':digest(media),'language':'en','timestamp_source':source,'words':word_rows})
    if any(w.end>actual['duration']+.1 for w in t.words):raise ValueError('WORD_TIMESTAMP_OUTSIDE_MEDIA')
    return t


def transcribe_local(media:Path,model_name='base.en')->Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError('pip install faster-whisper to enable OPTIONAL local ASR') from e
    with tempfile.TemporaryDirectory(prefix='podcast_asr_') as td:
        wav=Path(td)/'audio.wav'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(media),'-vn','-ac','1','-ar','16000',str(wav)],check=True)
        model=WhisperModel(model_name,device='cpu',compute_type='int8')
        segs,info=model.transcribe(str(wav),language='en',word_timestamps=True,vad_filter=False)
        rows=[]
        for seg in segs:
            for word in seg.words or []:
                if word.start is not None and word.end is not None:
                    rows.append({'start':word.start,'end':word.end,'text':word.word.strip(),
                                 'speaker':'unknown','confidence':word.probability})
    if not rows:raise ValueError('ASR_EMPTY: manual inspection needed')
    return from_words(media,rows,source='ASR_WORDS')


def main():
    p=argparse.ArgumentParser();p.add_argument('--media',type=Path,required=True)
    p.add_argument('--input-words',type=Path,help='JSON list of {start,end,text,speaker?,confidence?}')
    p.add_argument('--local-asr',action='store_true');p.add_argument('--model',default='base.en')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if bool(args.input_words)==bool(args.local_asr):raise ValueError('Choose exactly one: --input-words or --local-asr')
    t=from_words(args.media,json.loads(args.input_words.read_text(encoding='utf8'))) if args.input_words else transcribe_local(args.media,args.model)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(t.model_dump_json(indent=2),encoding='utf8')
    print(json.dumps({'words':len(t.words),'output':str(args.output)}))
if __name__=='__main__':main()
