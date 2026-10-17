import os, sys, json, re, urllib.request, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from podcast_media import probe

def hex_to_ass(hex_color: str) -> str:
    h = hex_color.lstrip('#')
    return f"&H00{h[4:6].upper()}{h[2:4].upper()}{h[0:2].upper()}&"

def ts_ass(seconds: float) -> str:
    n = int(round(seconds * 100))
    h, n = divmod(n, 360000)
    m, n = divmod(n, 6000)
    s, c = divmod(n, 100)
    return f"{h}:{m:02}:{s:02}.{c:02}"

def tag_dialogue_roles(words: list[dict], model="gpt-5.6-sol") -> list[dict]:
    prompt = """You are an expert dialogue editor for real-world police bodycam / patrol encounters.
Classify each word index into the speaking role:
- "COP" (Police officer / Deputy / Air1)
- "SUSPECT" (Suspect / Citizen / Detainee, e.g. Travis, Biker, Driver)

Return a JSON array of turns covering all words from index 0 to {total_words}-1:
[
  {"start_idx": 0, "end_idx": 9, "role": "COP"},
  {"start_idx": 10, "end_idx": 15, "role": "SUSPECT"}
]
Rules:
1. Cover every single index from 0 to {total_words}-1 consecutively.
2. end_idx is inclusive.
3. Output valid JSON array only, no other text.
""".replace("{total_words}", str(len(words)))

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are a precise JSON dialogue segmenter.'},
            {'role': 'user', 'content': prompt + "\n\nWORDS:\n" + json.dumps([{"i": i, "w": w["text"]} for i, w in enumerate(words)])}
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
    
    # Map role back to words
    word_roles = ["COP"] * len(words)
    for t in turns:
        st = t.get("start_idx", 0)
        ed = t.get("end_idx", len(words) - 1)
        role = t.get("role", "COP").upper()
        for i in range(st, min(ed + 1, len(words))):
            word_roles[i] = role
            
    for i, w in enumerate(words):
        w["role"] = word_roles[i]
        
    return words

def build_viral_chunks(words: list[dict], max_words=3, max_gap=0.35) -> list[dict]:
    chunks = []
    block = []
    for w in words:
        if block:
            gap = w["start"] - block[-1]["end"]
            role_changed = (w.get("role") != block[-1].get("role"))
            if len(block) >= max_words or gap > max_gap or role_changed:
                chunks.append(block)
                block = []
        block.append(w)
        if w["text"].rstrip().endswith((".", "?", "!")):
            chunks.append(block)
            block = []
    if block:
        chunks.append(block)

    events = []
    for idx, c in enumerate(chunks, 1):
        st = c[0]["start"]
        ed = c[-1]["end"]
        if ed <= st:
            ed = round(st + 0.3, 3)
        role = c[0].get("role", "COP")
        # Clean text and force uppercase
        clean_words = [re.sub(r'[^\w\s\'-]', '', w["text"]).strip().upper() for w in c]
        clean_words = [w for w in clean_words if w]
        text = " ".join(clean_words)
        if text:
            events.append({
                "id": f"ev{idx:03d}",
                "start": round(st, 3),
                "end": round(ed, 3),
                "role": role,
                "text": text
            })
    return events

def generate_viral_ass(events: list[dict], width=1080, height=1920, out_path=Path("captions_viral.ass")) -> Path:
    # Role styling:
    # COP -> Red (&H003333FF& in BGR ASS: Red=00, Green=33, Blue=FF -> &H000000FF& is pure red)
    # Pure red in ASS: &H000000FF&
    # SUSPECT / BIKER -> Neon Green (&H0000FF33& or &H0033FF33&)
    role_colors = {
        "COP": "&H002222FF&",       # Bright Red
        "SUSPECT": "&H0033FF33&",   # Neon Green
        "BIKER": "&H0033FF33&",     # Neon Green
        "DRIVER": "&H0033FF33&",    # Neon Green
        "CITIZEN": "&H00FFCC00&"    # Cyan / Yellow
    }

    y_pos = int(height * 0.76) # ~1460px
    x_pos = width // 2

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Default style: Montserrat / Arial Black / Inter Bold
        "Style: Default,Arial Black,58,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,1,0,0,100,100,0,0,1,5.0,2.0,2,20,20,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for ev in events:
        role = ev["role"]
        role_color = role_colors.get(role, "&H0033FF33&")
        tag_text = f"{role}:"
        body_text = ev["text"]
        
        # Dialogue line with colored tag on top line, bold white text on bottom line
        dialogue = (
            f"Dialogue: 0,{ts_ass(ev['start'])},{ts_ass(ev['end'])},Default,,0,0,0,,"
            f"{{\\pos({x_pos},{y_pos})\\an2}}"
            f"{{\\fs36\\b1\\i1\\c{role_color}\\3c&H00000000&\\bord3}}{tag_text}\\N"
            f"{{\\fs62\\b1\\i1\\c&H00FFFFFF&\\3c&H00000000&\\bord5.5\\shad2}}{body_text}"
        )
        lines.append(dialogue)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path

def render_viral_clip(folder: Path, out_name="final_viral_role_captions.mp4") -> dict:
    folder = Path(folder).resolve()
    clip_file = folder / "clip.mp4"
    tx_file = folder / "clip_transcript.json"
    
    info = probe(clip_file)
    tx = json.loads(tx_file.read_text(encoding="utf-8"))
    
    print(f"Tagging dialogue roles with gpt-5.6-sol for {folder.name}...")
    tagged_words = tag_dialogue_roles(tx["words"])
    (folder / "tagged_words.json").write_text(json.dumps(tagged_words, indent=2), encoding="utf-8")
    
    events = build_viral_chunks(tagged_words)
    (folder / "viral_events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    print(f"Created {len(events)} viral role chunks.")
    
    ass_file = folder / "captions_viral.ass"
    generate_viral_ass(events, info["width"], info["height"], ass_file)
    print(f"Generated ASS: {ass_file}")
    
    out_file = folder / out_name
    ass_path_escaped = str(ass_file).replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'").replace(',', '\\,')
    vf = f"ass='{ass_path_escaped}'"
    
    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-i', str(clip_file),
        '-map', '0:v:0', '-map', '0:a:0',
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-c:a', 'copy',
        '-movflags', '+faststart',
        str(out_file)
    ]
    
    print(f"Rendering {out_file.name} with FFmpeg (stream copying native audio)...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("FFMPEG_FAILED: " + res.stderr)
        
    out_info = probe(out_file)
    print(f"DONE: {out_file.name} rendered successfully! ({out_info['width']}x{out_info['height']}, {out_info['duration']:.2f}s)")
    return {"out_file": str(out_file), "info": out_info, "events": len(events)}

if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("vso_clip_001")
    render_viral_clip(folder)
