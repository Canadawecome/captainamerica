#!/usr/bin/env python3
"""Podcast recut planning from true source transcript, keeping speaker sentences intact.

No automatic publication and no assumption that Opus reordered clip can be
extended simply by padding its own timeline. Always recut ORIGINAL source.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from opus_recut_engine import proposal,render
from podcast_contracts import Transcript
from podcast_media import probe,digest


def boundary_plan(folder:Path,attempt:int=1):
    folder=folder.resolve()
    review=json.loads((folder/'post_review.json').read_text(encoding='utf8'))
    if not review.get('recut_instruction'):
        raise ValueError('NO_RECUT_REASON_FROM_GPT')
    refs=json.loads((folder/'source_ref.json').read_text(encoding='utf8'))
    source=Path(refs['source_media']);original=Transcript.model_validate_json(Path(refs['source_transcript']).read_text())
    if original.media_sha256!=digest(source):raise ValueError('STALE_ORIGINAL_TRANSCRIPT')
    mapping=json.loads((folder/'source_mapping.json').read_text(encoding='utf8'))
    ranges=mapping.get('source_ranges_sec',[])
    if len(ranges)!=1:
        raise ValueError('MULTI_RANGE_OPUS_REORDER_REQUIRES_HUMAN_EDL')
    start,end=map(float,ranges[0]);words=original.words
    # Re-anchor to nearest sentence boundary with a conservative max 10 sec.
    prior=[w.end for w in words if start-10<=w.end<=start+.1 and w.text.rstrip().endswith(('.','?','!'))]
    later=[w.end for w in words if end-.1<=w.end<=end+10 and w.text.rstrip().endswith(('.','?','!'))]
    if start<=.10:prior.append(0.0)
    if not prior or not later:
        raise ValueError('SOURCE_SENTENCE_BOUNDARIES_UNVERIFIED: editor must supply reviewed EDL')
    a=max(prior);b=min(later)
    if b-a<=65:raise ValueError('RECUT_TOO_SHORT; seek longer complete episode section')
    p=proposal([a,b],review['recut_instruction'],attempt=attempt,pad_start=0,pad_end=0,
               source_total=probe(source)['duration'])
    p['source_sha256']=digest(source);p['clip_folder']=str(folder)
    p['source_sentence_boundary_evidence']={'start_from_transcript':a,'end_from_transcript':b}
    return p


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('plan');a.add_argument('--folder',type=Path,required=True);a.add_argument('--attempt',type=int,default=1);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('render');a.add_argument('--source',type=Path,required=True);a.add_argument('--plan',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--approved-boundary',action='store_true')
    x=p.parse_args()
    if x.action=='plan':
        data=boundary_plan(x.folder,x.attempt);x.output.parent.mkdir(parents=True,exist_ok=True)
        x.output.write_text(json.dumps(data,indent=2),encoding='utf8')
        print(json.dumps(data,indent=2))
    else:print(json.dumps(render(x.source,json.loads(x.plan.read_text()),x.output,approved_boundary=x.approved_boundary),indent=2))
if __name__=='__main__':main()
