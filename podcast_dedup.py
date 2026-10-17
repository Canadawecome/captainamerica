"""Near-duplicate podcast stories across approved exports, using actual word transcripts.

Helps avoid posting repeated conversational content; not an originality-evasion tool.
"""
from __future__ import annotations
from pathlib import Path
from podcast_contracts import Transcript
from podcast_media import digest
import json


def shingles(words,gram=6):
    items=[w.text.lower().strip('.,;:!?\"\'') for w in words]
    return {tuple(items[i:i+gram]) for i in range(max(0,len(items)-gram+1))}

def similarity(a,b):
    first=shingles(a.words);second=shingles(b.words)
    # Require sufficient diversity; identical boilerplate shouldn't automatically block.
    if min(len(first),len(second))<30:return 0.0
    return len(first & second)/min(len(first),len(second))

def duplicates(folder:Path,threshold=.83):
    folder=Path(folder)
    tx=Transcript.model_validate_json((folder/'clip_transcript.json').read_text(encoding='utf8'))
    findings=[]
    for other in sorted(folder.parent.glob('*/approval.json')):
        if other.parent==folder:continue
        try:
            a=json.loads(other.read_text(encoding='utf8'))
            if a.get('status')!='APPROVED':continue
            t_path=other.parent/'clip_transcript.json'
            if digest(t_path)!=a['transcript_sha256']:continue
            candidate=Transcript.model_validate_json(t_path.read_text(encoding='utf8'))
            ratio=similarity(tx,candidate)
            if ratio>=threshold:
                findings.append({'folder':other.parent.name,'overlap_score':round(ratio,3)})
        except (OSError,ValueError,KeyError):continue
    return findings
