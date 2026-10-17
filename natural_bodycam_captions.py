import os, sys, json, re, urllib.request, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from podcast_media import probe

def ts_ass(seconds: float) -> str:
    n = int(round(seconds * 100))
    h, n = divmod(n, 360000)
    m, n = divmod(n, 6000)
    s, c = divmod(n, 100)
    return f"{h}:{m:02}:{s:02}.{c:02}"

def analyze_dialogue_with_sol(words: list[dict], candidate_info: str = "") -> list[dict]:
    """Use gpt-5.6-sol to detect exact character roles (e.g. OFFICER, TRAVIS, AIR1) and emotional emphasis words."""
    prompt = f"""You are a professional video editor for viral police bodycam Shorts (Code Blue Cam, PoliceActivity).
Analyze this transcript segment:
Context: {candidate_info}

Tasks:
1. Assign exact speaker names/roles:
   - "OFFICER" (or "DEPUTY" or "AIR1" if helicopter)
   - Specific named suspect: "TRAVIS" (if suspect is Travis) or "DRIVER" / "SUSPECT"
   - "DISPATCH" (if radio/dispatch)
2. Identify EMPHASIS words: words spoken with intense stress, shock, accusations, or denials (e.g. LIE, JAIL, TOUCHING, VIDEO, STOP, SWEAR).

Return JSON array covering all words from index 0 to {len(words)-1}:
[
  {{
    "start_idx": 0,
    "end_idx": 9,
    "speaker": "OFFICER",
    "emphasis_indices": [2, 5, 6]
  }},
  ...
]
Rules:
- Cover every word index 0 to {len(words)-1} consecutively without gaps.
- Return ONLY valid JSON array.
"""
    payload = {
        'model': 'gpt-5.6-sol',
        'messages': [
            {'role': 'system', 'content': 'You are a precise JSON dialogue analyzer for viral short-form videos.'},
            {'role': 'user', 'content': prompt + "\n\nWORDS:\n" + json.dumps([{"i": i, "w": w["text"], "t": w["start"]} for i, w in enumerate(words)])}
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

    word_speaker = ["OFFICER"] * len(words)
    word_emphasis = [False] * len(words)

    for t in turns:
        st = t.get("start_idx", 0)
        ed = min(t.get("end_idx", len(words) - 1), len(words) - 1)
        spk = t.get("speaker", "OFFICER").upper()
        emp_list = t.get("emphasis_indices", [])
        for i in range(st, ed + 1):
            word_speaker[i] = spk
            if i in emp_list:
                word_emphasis[i] = True

    for i, w in enumerate(words):
        w["speaker"] = word_speaker[i]
        w["is_emphasis"] = word_emphasis[i]

    return words

def build_karaoke_events(words: list[dict], max_words_per_group=3, max_gap=0.35) -> list[dict]:
    """Group words into conversational phrases, and generate active word highlight moments."""
    groups = []
    block = []
    for w in words:
        if block:
            gap = w["start"] - block[-1]["end"]
            spk_changed = (w.get("speaker") != block[-1].get("speaker"))
            if len(block) >= max_words_per_group or gap > max_gap or spk_changed:
                groups.append(block)
                block = []
        block.append(w)
        if w["text"].rstrip().endswith((".", "?", "!")):
            groups.append(block)
            block = []
    if block:
        groups.append(block)

    karaoke_events = []
    for g in groups:
        spk = g[0].get("speaker", "OFFICER")
        g_start = g[0]["start"]
        g_end = g[-1]["end"]
        if g_end <= g_start:
            g_end = round(g_start + 0.3, 3)

        # Clean words
        clean_g = []
        for w in g:
            t = re.sub(r'[^\w\s\'-]', '', w["text"]).strip().upper()
            if not t:
                t = w["text"].strip().upper()
            clean_g.append({"text": t, "start": w["start"], "end": w["end"], "is_emphasis": w.get("is_emphasis", False)})

        # Each word gets an active interval
        for active_idx, target_word in enumerate(clean_g):
            w_start = target_word["start"]
            # Word duration extends to next word start or group end
            if active_idx + 1 < len(clean_g):
                w_end = clean_g[active_idx + 1]["start"]
            else:
                w_end = target_word["end"]
            if w_end <= w_start:
                w_end = round(w_start + 0.25, 3)

            # Build formatted display text:
            # Active word has yellow glow + slight scale: {\c&H0000FFFF&\fscx108\fscy108}WORD{\r}
            # Or if it's an emphasis word, high-voltage red/yellow
            phrase_parts = []
            for j, other_w in enumerate(clean_g):
                txt = other_w["text"]
                if j == active_idx:
                    if other_w["is_emphasis"]:
                        # High intensity yellow/gold highlight with scale
                        phrase_parts.append(f"{{\\c&H0000E6FF&\\3c&H00000000&\\fscx112\\fscy112\\bord6}}{txt}{{\\r}}")
                    else:
                        # Crisp bright yellow karaoke highlight
                        phrase_parts.append(f"{{\\c&H0022FFFF&\\3c&H00000000&\\fscx108\\fscy108\\bord5.5}}{txt}{{\\r}}")
                else:
                    # Inactive word in clean off-white
                    phrase_parts.append(f"{{\\c&H00F0F0F0&\\3c&H00000000&\\bord5}}{txt}")

            rendered_phrase = " ".join(phrase_parts)
            karaoke_events.append({
                "start": round(w_start, 3),
                "end": round(w_end, 3),
                "speaker": spk,
                "formatted_text": rendered_phrase
            })

    return karaoke_events

def generate_natural_ass(events: list[dict], width=1080, height=1920, out_path=Path("captions_natural.ass")) -> Path:
    speaker_colors = {
        "OFFICER": "&H002222FF&",  # Bright Red
        "DEPUTY": "&H002222FF&",   # Bright Red
        "COP": "&H002222FF&",      # Bright Red
        "TRAVIS": "&H0033FF33&",   # Neon Green
        "SUSPECT": "&H0033FF33&",  # Neon Green
        "DRIVER": "&H0033FF33&",   # Neon Green
        "BIKER": "&H0033FF33&",    # Neon Green
        "AIR1": "&H00FFFF00&",     # Cyan / Sky
        "DISPATCH": "&H00FFAA00&"  # Orange/Amber
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
        # Default style for active line
        "Style: Default,Arial Black,60,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,1,0,0,100,100,0,0,1,5.5,2.0,2,20,20,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for ev in events:
        spk = ev["speaker"]
        spk_color = speaker_colors.get(spk, "&H0033FF33&")
        tag_text = f"{spk}:"
        body_text = ev["formatted_text"]
        
        dialogue = (
            f"Dialogue: 0,{ts_ass(ev['start'])},{ts_ass(ev['end'])},Default,,0,0,0,,"
            f"{{\\pos({x_pos},{y_pos})\\an2}}"
            f"{{\\fs36\\b1\\i1\\c{spk_color}\\3c&H00000000&\\bord3.5}}{tag_text}\\N"
            f"{body_text}"
        )
        lines.append(dialogue)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path

def render_natural_clip(folder: Path, out_name="final_natural_karaoke.mp4") -> dict:
    folder = Path(folder).resolve()
    clip_file = folder / "clip.mp4"
    tx_file = folder / "clip_transcript.json"
    
    info = probe(clip_file)
    tx = json.loads(tx_file.read_text(encoding="utf-8"))
    
    print(f"[{folder.name}] Analyzing natural dialogue & emphasis with gpt-5.6-sol...")
    annotated_words = analyze_dialogue_with_sol(tx["words"], f"Folder {folder.name}, duration: {info['duration']}s")
    
    events = build_karaoke_events(annotated_words)
    print(f"[{folder.name}] Generated {len(events)} kinetic karaoke highlight steps.")
    
    ass_file = folder / "captions_natural.ass"
    generate_natural_ass(events, info["width"], info["height"], ass_file)
    
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
    
    print(f"[{folder.name}] Rendering {out_file.name} with FFmpeg...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("FFMPEG_FAILED: " + res.stderr)
        
    out_info = probe(out_file)
    print(f"[{folder.name}] SUCCESS: Rendered {out_file.name} ({out_info['width']}x{out_info['height']}, {out_info['duration']:.2f}s)")
    return {"out_file": str(out_file), "info": out_info, "events": len(events)}

if __name__ == "__main__":
    for f in ["vso_clip_001", "vso_clip_002", "vso_clip_003"]:
        render_natural_clip(Path(f))
