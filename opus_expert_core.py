#!/usr/bin/env python3
"""Shared v1.1/v3.7 OpusClip Expert Cut primitives.

Provider customPrompt describes content only. Technical settings live in curationPref
and renderPref. Bundling is conservative; never claim the number of Opus credits.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path

MIN_DURATION_EXCLUSIVE=65.0
STOPWORDS={'a','an','the','is','i','it','and','or','to','of','in','on','for','that','this','we','they','you','he','she','was','are'}


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def normalize_words(t):
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?",t.lower().replace('’',"'"))


def phrase_present(hook:str,text:str,min_content_words:int=3)->bool:
    """Exact contiguous phrase match; single pronoun cannot validate a GPT claim."""
    hook_tokens=normalize_words(hook);tokens=normalize_words(text)
    if len([w for w in hook_tokens if w not in STOPWORDS])<min_content_words:
        return False
    n=len(hook_tokens)
    return n<=len(tokens) and any(tokens[i:i+n]==hook_tokens for i in range(len(tokens)-n+1))


def windows_overlap(a,b):
    return max(0.,min(a[1],b[1])-max(a[0],b[0]))


def bundle_candidates(candidates,max_span:float=240.,max_gap:float=20.,max_per_bundle:int=3):
    """Group only adjacent/overlapping source intervals; independent topics stay split.

    candidates: dict items with id, start,end, prompt and score; no overlong bundles.
    """
    ordered=sorted(candidates,key=lambda c:(float(c['start']),-float(c.get('score',0))))
    bundles=[]
    for c in ordered:
        a=float(c['start']);b=float(c['end'])
        if b<=a or b-a<MIN_DURATION_EXCLUSIVE:
            raise ValueError('Candidate source window must be >65 seconds')
        if bundles and len(bundles[-1]['candidate_ids'])<max_per_bundle:
            last=bundles[-1]
            if a-last['end']<=max_gap and max(last['end'],b)-last['start']<=max_span:
                last['end']=max(last['end'],b)
                last['candidate_ids'].append(c['id'])
                last['candidate_prompts'].append(c['prompt'])
                last['scores'].append(c.get('score',0))
                continue
        bundles.append({'start':a,'end':b,'candidate_ids':[c['id']],
                        'candidate_prompts':[c['prompt']],'scores':[c.get('score',0)]})
    for i,group in enumerate(bundles,1):
        group['group_id']=f'group_{i:03d}'
        group['score']=max(group['scores'])
    return bundles


def opus_render_profile(kind:str, enable_local_captions=True):
    if kind not in ('podcast','asmr'):raise ValueError('Unknown preset')
    # Relevant switches are documented in export render preferences. Account-specific
    # brand template choices must be validated before live submission.
    base={'layoutAspectRatio':'portrait', 'enableCaption':not enable_local_captions,
          'enableEmoji':False,'enableBroll':False,
          'quickstartConfig':{'enableRemoveFillerWords':False}}
    if kind=='podcast':base['enableSplitLayout']=True
    return base


def make_opus_jobs(groups,video_url:str,kind:str,target_max=100):
    if not video_url.startswith(('https://','http://')):
        raise ValueError('Network accessible source URL required')
    output=[]
    for group in groups:
        span=group['end']-group['start']
        if span<70:continue
        # Always request >=70 seconds; a narrower source range may produce less in
        # practice, hence mandatory FFprobe after export.
        high=max(70,min(int(span),target_max))
        candidate_prompts=group['candidate_prompts'][:3]
        content_prompt=('Find the strongest self-contained '+('conversation' if kind=='podcast' else 'metalworking process')+
                        ' within these themes: '+' | '.join(candidate_prompts))
        req={'videoUrl':video_url,
             'curationPref':{'model':'ClipAnything','range':{'startSec':group['start'],'endSec':group['end']},
                             'clipDurations':[[70,high]],'customPrompt':content_prompt[:1500]},
             'renderPref':opus_render_profile(kind)}
        output.append({'group_id':group['group_id'],'candidate_ids':group['candidate_ids'],
                       'source_window':[group['start'],group['end']],'request':req,
                       'requires_post_export_review':True})
    return {'schema_version':'opus-expert-v1','kind':kind,'jobs':output,
            'unique_projects_upper_bound':len(output),
            'note':'Grouping may reduce submissions; actual API credit charges/pricing are account-specific and unverified.'}


def transcript_boundaries(word_rows: list, duration:float):
    """Boundary indications only, not semantic proof of a complete thought."""
    if not word_rows:return {'has_words':False,'risk':['NO_TRANSCRIPT']}
    first=word_rows[0];last=word_rows[-1]
    fst=float(first['start'] if isinstance(first,dict) else first.start)
    last_end=float(last['end'] if isinstance(last,dict) else last.end)
    last_text=str(last['text'] if isinstance(last,dict) else last.text)
    gap=max(0,duration-last_end)
    risk=[]
    if fst>4:risk.append('DELAYED_FIRST_WORD')
    # ASR punctuation is not ground truth, never reject based on punctuation alone.
    if gap<.18 and not last_text.rstrip().endswith(('.','!','?')):risk.append('POSSIBLE_CUT_OFF_REVIEW_AUDIO')
    if gap>9:risk.append('LONG_TAIL_WITHOUT_DIALOGUE')
    return {'has_words':True,'first_word_sec':fst,'last_word_end_sec':last_end,
            'tail_pause_sec':round(gap,3),'last_has_punctuation':last_text.rstrip().endswith(('.','!','?')),
            'risk':risk,'requires_semantic_review':True}


def signed_receipt(clip_path,source_map_path,review_path,status:str):
    return {'policy':'opus-expert-v1','clip_sha256':sha256(clip_path),
            'mapping_sha256':sha256(source_map_path),'review_sha256':sha256(review_path),'status':status}
