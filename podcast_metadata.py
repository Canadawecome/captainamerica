#!/usr/bin/env python3
"""Optional grounded English metadata draft from actual approved podcast transcript.

Never changes spoken voice, facts, or footage. Editor reviews before publishing.
"""
import argparse,json
from pathlib import Path
from podcast_director import require_approved,transcript
from podcast_gpt import ask

PROMPT='''You write a concise US/UK English short-form podcast title, description and 4-5 niche hashtags.
Only describe the exact uploaded transcript; do not invent identities, quotes, statistics,
claims or speaker credentials. No spam, no deceptive clickbait or unverified medical/financial advice.
JSON ONLY: {"title":"...","description":"...","hashtags":["#podcast", "#specificTopic",...] }.
These are editorial DRAFTS requiring final human review; no claim of virality.'''

def generate(folder:Path,model:str):
    require_approved(folder)
    folder=folder.resolve()
    t=transcript(folder/'clip_transcript.json',folder/'clip.mp4')
    dialogue=' '.join(w.text.strip() for w in t.words)
    data=ask(model,PROMPT,dialogue)
    if not isinstance(data.get('hashtags'),list) or not 3<=len(data['hashtags'])<=6:
        raise ValueError('Invalid metadata output')
    if not data.get('title') or not data.get('description'):
        raise ValueError('No title/description returned')
    (folder/'title.txt').write_text(data['title'].strip()+'\n',encoding='utf8')
    (folder/'description.txt').write_text(data['description'].strip()+'\n',encoding='utf8')
    (folder/'hashtags.txt').write_text(' '.join(data['hashtags'])+'\n',encoding='utf8')
    return {'status':'DRAFT_NEEDS_EDITOR_REVIEW','title':data['title']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--model',required=True)
    a=p.parse_args();print(json.dumps(generate(a.folder,a.model),indent=2))
