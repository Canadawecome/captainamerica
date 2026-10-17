import os, json, urllib.request
from dotenv import load_dotenv

load_dotenv()

tx = json.load(open('vso_clip_001/clip_transcript.json', encoding='utf-8'))
words = tx['words']

prompt = """You are an expert dialogue editor for police bodycam / patrol reality videos.
Given the words and timestamps of this clip, identify the dialogue turns and assign each to the correct character role:
- "COP" (The police officer / deputy)
- "SUSPECT" (The citizen / suspect, e.g. Travis)

Return a JSON array of turns:
[
  {
    "start_word_index": 0,
    "end_word_index": 12,
    "speaker_role": "COP",
    "text": "..."
  },
  ...
]
Rules:
1. Cover every single word from index 0 to {total_words}-1 consecutively without gaps or overlap.
2. end_word_index is inclusive.
3. Output valid JSON only, no markdown.
""".replace("{total_words}", str(len(words)))

payload = {
    'model': 'gpt-5.6-sol',
    'messages': [
        {'role': 'system', 'content': 'You are a precise JSON dialogue segmenter.'},
        {'role': 'user', 'content': prompt + "\n\nWORDS:\n" + json.dumps([{"idx": i, "w": w["text"], "t": w["start"]} for i, w in enumerate(words)])}
    ],
    'max_tokens': 4000
}

req = urllib.request.Request(
    os.environ['OPENAI_BASE_URL'] + '/chat/completions',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'], 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)

res = json.loads(urllib.request.urlopen(req, timeout=60).read())
content = res['choices'][0]['message']['content']
print("Response preview:")
print(content[:600])
