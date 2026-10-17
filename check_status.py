import os, urllib.request, json, time
from dotenv import load_dotenv

load_dotenv()
token = os.environ['OPUSCLIP_API_KEY']
pids = ['P3101714WouP', 'P3101714WviL', 'P3101714Wwwx']

for pid in pids:
    req = urllib.request.Request(
        f'https://api.opus.pro/api/clip-projects/{pid}',
        headers={'Authorization': 'Bearer ' + token, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        payload = data.get('data', data)
        stage = payload.get('stage')
        progress = payload.get('progress')
        print(f"Project {pid}: stage = {stage}, progress = {progress}")
    except Exception as e:
        print(f"Project {pid}: error = {e}")
