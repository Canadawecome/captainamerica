import os, json, urllib.request, re
from dotenv import load_dotenv

load_dotenv()

with open('vso_clip_002/clip_transcript.json', 'r', encoding='utf-8') as f:
    tx = json.load(f)
words = tx['words']

prompt = f"""You are an expert dialogue editor for real-world police bodycam / patrol encounters.
In this scene, a police officer arrives at a lake boat ramp, urgently asking a boat owner / citizen about a suspect fleeing by boat, and asking to use their airboat to pursue the suspect.

Classify each word index into the speaking role:
- "COP" (The police officer / deputy who is asking questions and coordinating pursuit)
- "CITIZEN" (The boat owner / civilian at the boat ramp who answers questions and helps launch the airboat)

Return a JSON array of turns covering all words from index 0 to {len(words)-1}:
[
  {{"start_idx": 0, "end_idx": 9, "role": "COP"}},
  {{"start_idx": 10, "end_idx": 25, "role": "CITIZEN"}}
]
Rules:
1. Cover every single index from 0 to {len(words)-1} consecutively.
2. end_idx is inclusive.
3. Output valid JSON array only, no other text.
"""

payload = {
    'model': 'gpt-5.6-sol',
    'messages': [
        {'role': 'system', 'content': 'You are a precise JSON dialogue segmenter.'},
        {'role': 'user', 'content': prompt + '\n\nWORDS:\n' + json.dumps([{'i': i, 'w': w['text']} for i, w in enumerate(words)])}
    ],
    'max_tokens': 4000
}

req = urllib.request.Request(
    os.environ['OPENAI_BASE_URL'] + '/chat/completions',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'], 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)

with urllib.request.urlopen(req, timeout=60) as resp:
    res = json.loads(resp.read())

text = res['choices'][0]['message'].get('content') or ''
text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.I).strip()
try:
    turns = json.loads(text)
except Exception:
    m = re.search(r'\[.*\]', text, re.DOTALL)
    turns = json.loads(m.group(0)) if m else []

word_roles = ['COP'] * len(words)
for t in turns:
    st = t.get('start_idx', 0)
    ed = t.get('end_idx', len(words) - 1)
    role = t.get('role', 'COP').upper()
    for i in range(st, min(ed + 1, len(words))):
        word_roles[i] = role

for i, w in enumerate(words):
    w['role'] = word_roles[i]

with open('vso_clip_002/tagged_words.json', 'w', encoding='utf-8') as f:
    json.dump(words, f, indent=2)

print('Successfully re-tagged vso_clip_002 with gpt-5.6-sol!')
counts = {}
for w in words:
    counts[w['role']] = counts.get(w['role'], 0) + 1
print('Role counts:', counts)
