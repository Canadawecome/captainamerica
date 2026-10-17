#!/usr/bin/env python3
"""Native-English podcast director. GPT recommends, Opus cuts, GPT reviews the REAL export.

No original voice rewriting or ElevenLabs stage exists here. All review outcomes
are heuristic quality choices, NOT measured prediction of views.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
from podcast_contracts import Transcript,PrecutPlan,PostReview,Approval
from podcast_media import probe,digest
from opus_expert_core import phrase_present, bundle_candidates, make_opus_jobs, transcript_boundaries

MIN_EXCLUSIVE=65.0
TARGET_MIN=70
TARGET_MAX=100


def read(file:Path):return json.loads(Path(file).read_text(encoding='utf8'))

def transcript(path:Path,media:Path)->Transcript:
    tx=Transcript.model_validate(read(path))
    if not Path(media).is_file() or tx.media_sha256!=digest(media):
        raise ValueError('STALE_TRANSCRIPT: words not matched to actual MP4')
    if tx.language not in ('en','en-US','en-GB'):raise ValueError('ENGLISH_SOURCE_ONLY')
    return tx


def validate_precut(media:Path,source_transcript:Path,plan_path:Path):
    source=probe(media); t=transcript(source_transcript,media)
    plan=PrecutPlan.model_validate(read(plan_path))
    if plan.source_sha256!=digest(media) or plan.transcript_sha256!=digest(source_transcript):
        raise ValueError('STALE_PRECUT_PLAN')
    if not plan.rights_verified:raise ValueError('RIGHTS_NOT_VERIFIED')
    if not source['has_audio']:raise ValueError('MISSING_ORIGINAL_PODCAST_AUDIO')
    valid=[]
    for c in plan.candidates:
        duration=c.end-c.start
        if duration<70 or duration>TARGET_MAX+.01 or c.end>source['duration']+.08:
            raise ValueError(f'BAD_CANDIDATE_DURATION: {c.id}, expect 70-100s source')
        words=[w for w in t.words if w.start>=c.start-.05 and w.end<=c.end+.05]
        if len(words)<45:raise ValueError('NOT_ENOUGH_SOURCE_DIALOGUE: '+c.id)
        if not phrase_present(c.hook_quote,' '.join(w.text for w in words[:24]),min_content_words=3):
            raise ValueError('HOOK_NOT_EVIDENCED_IN_TRANSCRIPT: '+c.id)
        valid.append(c)
    return plan,t,source


def opus_jobs(media:Path,tx:Path,plan:Path,url:str)->dict:
    checked,_,_=validate_precut(media,tx,plan)
    rows=[]
    for c in checked.candidates:
        rows.append({'id':c.id,'start':c.start,'end':c.end,'score':c.predicted_potential_score,
                     'prompt':(f'Find the English podcast discussion where a speaker says "{c.hook_quote}" '
                               f'and develops the point toward "{c.payoff_quote}". '
                               f'Important context: {c.why_compelling}.')})
    packages=make_opus_jobs(bundle_candidates(rows,max_span=220,max_gap=18),'https://placeholder.test','podcast',100)
    for j in packages['jobs']:
        j['request']['videoUrl']=url
        j['source_interval_sec']=j['source_window']
    # Versioned result: an Opus project can hold >1 proposed moment. Mapping must
    # resolve individual exported clips before anyone can approve publication.
    return {'schema_version':'podcast-v1.1','source_sha256':digest(media),
            'source_transcript_sha256':digest(tx),'plan_sha256':digest(plan),
            'jobs':packages['jobs'],'project_budget_plan':packages['unique_projects_upper_bound'],
            'credit_note':packages['note']}


def mapping_verified(mapping_path:Path,candidate)->bool:
    if not mapping_path.exists():return False
    try:
        m=read(mapping_path)
        if m.get('candidate_id')!=candidate.id:return False
        if m.get('verified_by') not in ('HUMAN_EDITOR','OPUS_PROVIDER'):return False
        if not m.get('reviewer_or_project_id'):return False
        ranges=m.get('source_ranges_sec',[])
        if not ranges or any(len(v)!=2 or v[1]<=v[0] for v in ranges):return False
        total=sum(b-a for a,b in ranges)
        inside=sum(max(0,min(b,candidate.end)-max(a,candidate.start)) for a,b in ranges)
        return total>0 and inside/total>=.75
    except (KeyError,TypeError,ValueError):return False


def semantic_boundaries(t:Transcript,duration:float)->dict:
    relevant=[w for w in t.words if w.start<duration]
    if not relevant:raise ValueError('NO_CLIP_WORDS')
    first=relevant[0];last=relevant[-1]
    return {'word_count':len(relevant),'first_word_at':first.start,
            'last_word_end':last.end,'last_punctuation':last.text.strip().endswith(('.', '?','!')),
            'coverage':min(1.,max(0.,(last.end-first.start)/duration))}


def review(clip_folder:Path,source_media:Path,source_tx:Path,precut:Path)->Approval:
    folder=Path(clip_folder).resolve();clip=folder/'clip.mp4'
    clip_info=probe(clip)
    duration=clip_info['duration']
    if not duration>MIN_EXCLUSIVE:
        raise ValueError(f'DURATION_RECUT: FFprobe {duration:.3f}s, must be >65.000s')
    if not clip_info['has_audio']:raise ValueError('ORIGINAL_AUDIO_MISSING')
    if clip_info['height']<=clip_info['width'] or abs(clip_info['width']/clip_info['height']-9/16)>.06:
        raise ValueError('PORTRAIT_REFRAME_NEEDED')
    clip_tx_path=folder/'clip_transcript.json'
    clip_tx=transcript(clip_tx_path,clip)
    plan,_,_=validate_precut(source_media,source_tx,precut)
    rpath=folder/'post_review.json';r=PostReview.model_validate(read(rpath))
    if r.clip_sha256!=digest(clip) or r.transcript_sha256!=digest(clip_tx_path):
        raise ValueError('STALE_POST_REVIEW')
    ids={c.id:c for c in plan.candidates}
    if r.candidate_id not in ids:raise ValueError('UNKNOWN_SOURCE_CANDIDATE')
    bounds=semantic_boundaries(clip_tx,duration)
    problems=[]
    if bounds['word_count']<55:problems.append('TOO_LITTLE_SPEECH')
    if bounds['first_word_at']>5.:problems.append('INTRO_DEAD_AIR')
    if duration-bounds['last_word_end']>9.:problems.append('EARLY_ENDING_OR_PADDING')
    boundary_signals=transcript_boundaries(clip_tx.words,duration)
    # Word punctuation alone is not proof of a truncation. Require semantic review.
    if 'POSSIBLE_CUT_OFF_REVIEW_AUDIO' in boundary_signals['risk'] and not r.ends_at_natural_boundary:
        problems.append('POSSIBLE_FINAL_SENTENCE_CUT_OFF')
    if bounds['coverage']<.65:problems.append('CONVERSATION_TOO_SPARSE')
    for field in ('complete_thought','meaning_not_distorted','begins_at_natural_boundary',
                  'ends_at_natural_boundary','clear_english_dialogue','speaker_framing_ok'):
        if not getattr(r,field):problems.append(field.upper()+'_FAILED')
    if r.review_confidence<.75:problems.append('LOW_MODEL_CONFIDENCE')
    from podcast_dedup import duplicates
    if duplicates(folder):problems.append('NEAR_DUPLICATE_APPROVED_STORY')
    if not r.rights_verified:problems.append('RIGHTS_REVIEW_MISSING')
    mapped=mapping_verified(folder/'source_mapping.json',ids[r.candidate_id])
    if not r.source_mapping_verified or not mapped:problems.append('SOURCE_MAPPING_UNVERIFIED')
    score=r.scores.total()
    if any(x in problems for x in ('RIGHTS_REVIEW_MISSING','SOURCE_MAPPING_UNVERIFIED','LOW_MODEL_CONFIDENCE')):
        status='HOLD'
    elif problems:status='RECUT'
    else:status='APPROVED' if score>=85 else 'RECUT' if score>=70 else 'REJECT'
    approval=Approval(status=status,score=score,blockers=problems,
       clip_sha256=digest(clip),transcript_sha256=digest(clip_tx_path),
       review_sha256=digest(rpath),plan_sha256=digest(precut),
       mapping_sha256=digest(folder/'source_mapping.json') if (folder/'source_mapping.json').exists() else 'MISSING',
       source_transcript_sha256=digest(source_tx))
    (folder/'approval.json').write_text(approval.model_dump_json(indent=2),encoding='utf8')
    (folder/'source_ref.json').write_text(json.dumps({'source_media':str(Path(source_media).resolve()),
       'source_transcript':str(Path(source_tx).resolve()),'precut':str(Path(precut).resolve())},indent=2),encoding='utf8')
    return approval


def require_approved(folder:Path):
    folder=Path(folder).resolve();p=folder/'approval.json'
    if not p.is_file():raise ValueError('PODCAST_APPROVAL_REQUIRED')
    a=Approval.model_validate(read(p))
    if a.status!='APPROVED':raise ValueError('PODCAST_NOT_APPROVED: '+a.status)
    refs=read(folder/'source_ref.json')
    pairs=[(folder/'clip.mp4',a.clip_sha256),(folder/'clip_transcript.json',a.transcript_sha256),
           (folder/'post_review.json',a.review_sha256),(folder/'source_mapping.json',a.mapping_sha256),
           (Path(refs['precut']),a.plan_sha256),(Path(refs['source_transcript']),a.source_transcript_sha256)]
    for file,hash_value in pairs:
        if not file.is_file() or digest(file)!=hash_value:raise ValueError('STALE_PODCAST_APPROVAL: '+str(file))
    info=probe(folder/'clip.mp4')
    if info['duration']<=MIN_EXCLUSIVE or not info['has_audio']:
        raise ValueError('DURATION_OR_AUDIO_GATE_FAIL')
    return a


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('opus-jobs');a.add_argument('--media',type=Path,required=True);a.add_argument('--transcript',type=Path,required=True);a.add_argument('--precut',type=Path,required=True);a.add_argument('--url',required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('review');a.add_argument('--clip-folder',type=Path,required=True);a.add_argument('--source-media',type=Path,required=True);a.add_argument('--source-transcript',type=Path,required=True);a.add_argument('--precut',type=Path,required=True)
    a=sub.add_parser('gate');a.add_argument('--clip-folder',type=Path,required=True)
    args=p.parse_args()
    if args.cmd=='opus-jobs':
        r=opus_jobs(args.media,args.transcript,args.precut,args.url)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(r,indent=2),encoding='utf8')
        print(json.dumps({'jobs':len(r['jobs']),'output':str(args.output)}))
    elif args.cmd=='review':print(review(args.clip_folder,args.source_media,args.source_transcript,args.precut).model_dump_json(indent=2))
    else:print(require_approved(args.clip_folder).model_dump_json(indent=2))
if __name__=='__main__':main()
