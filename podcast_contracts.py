"""English-native podcast contracts. No storytelling scripts or TTS exist in this branch."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Word(Strict):
    start: float=Field(ge=0)
    end: float=Field(gt=0)
    text: str=Field(min_length=1)
    speaker: str='unknown'
    confidence: float|None=Field(default=None,ge=0,le=1)
    @model_validator(mode='after')
    def check(self):
        if self.end<=self.start:raise ValueError('word start must precede end')
        return self

class Transcript(Strict):
    schema_version:Literal['podcast-v1']='podcast-v1'
    media_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
    language:Literal['en','en-US','en-GB']='en'
    timestamp_source:Literal['ASR_WORDS','PROVIDER_ALIGNED_WORDS','HUMAN_REVIEWED']='ASR_WORDS'
    words:list[Word]=Field(min_length=1)
    @model_validator(mode='after')
    def timestamps(self):
        ordered=sorted(self.words,key=lambda w:w.start)
        if any(w.start < a.start-1e-3 for a,w in zip(ordered,self.words)):
            raise ValueError('word timings not sorted')
        if any(right.start < left.start for left,right in zip(self.words,self.words[1:])):
            raise ValueError('word order mismatch')
        return self

class Candidate(Strict):
    id:str
    start:float=Field(ge=0)
    end:float=Field(gt=0)
    hook_quote:str=Field(min_length=8)
    payoff_quote:str=Field(min_length=5)
    transcript_evidence:str=Field(min_length=8)
    why_compelling:str=Field(min_length=12)
    predicted_potential_score:int=Field(ge=0,le=100)
    confidence:float=Field(ge=0,le=1)
    @model_validator(mode='after')
    def check(self):
        if self.end<=self.start:raise ValueError('candidate end before start')
        return self

class PrecutPlan(Strict):
    schema_version:Literal['podcast-v1']='podcast-v1'
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    transcript_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    rights_verified:bool=False
    candidates:list[Candidate]=Field(min_length=1)

class ReviewScores(Strict):
    hook:int=Field(ge=0,le=100)
    meaning:int=Field(ge=0,le=100)
    audio_emotion:int=Field(ge=0,le=100)
    framing:int=Field(ge=0,le=100)
    pacing:int=Field(ge=0,le=100)
    caption_readiness:int=Field(ge=0,le=100)
    def total(self):
        return round(self.hook*.25+self.meaning*.25+self.audio_emotion*.20+
                     self.framing*.15+self.pacing*.10+self.caption_readiness*.05,2)

class PostReview(Strict):
    schema_version:Literal['podcast-v1']='podcast-v1'
    candidate_id:str
    clip_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    transcript_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    scores:ReviewScores
    complete_thought:bool
    meaning_not_distorted:bool
    begins_at_natural_boundary:bool
    ends_at_natural_boundary:bool
    clear_english_dialogue:bool
    speaker_framing_ok:bool
    rights_verified:bool=False
    source_mapping_verified:bool=False
    review_confidence:float=Field(ge=0,le=1)
    evidence_note:str=Field(min_length=12)
    recut_instruction:str|None=None

class Approval(Strict):
    schema_version:Literal['podcast-v1']='podcast-v1'
    status:Literal['APPROVED','RECUT','REJECT','HOLD']
    score:float
    blockers:list[str]
    clip_sha256:str
    transcript_sha256:str
    review_sha256:str
    plan_sha256:str
    mapping_sha256:str
    source_transcript_sha256:str
