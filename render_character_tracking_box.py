import os, sys, json, re, subprocess
from pathlib import Path

# Add FFmpeg path
FFMPEG_DIR = r"C:\Users\ADMIN\.gemini\antigravity\scratch\local-video-forge\.venv\Scripts"
if FFMPEG_DIR not in os.environ['PATH']:
    os.environ['PATH'] = FFMPEG_DIR + ";" + os.environ['PATH']

def ts_ass(seconds: float) -> str:
    n = int(round(seconds * 100))
    h, n = divmod(n, 360000)
    m, n = divmod(n, 6000)
    s, c = divmod(n, 100)
    return f"{h}:{m:02}:{s:02}.{c:02}"

def build_punchy_chunks(words: list[dict], max_words=3, max_gap=0.35) -> list[dict]:
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
            ed = round(st + 0.35, 3)
        # Ensure minimum duration for ultra readability
        if ed - st < 0.28:
            ed = round(st + 0.28, 3)
            
        role = c[0].get("role", "COP").upper()
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

# Trajectory generators for each clip
def get_clip_trajectory(clip_name: str, duration: float):
    if "001" in clip_name:
        # vso_clip_001 (Beach scene):
        # COP: Officer in khaki uniform
        # 0s - 24s: Standing at left (X: 270, Y: 1120)
        # 24s - 36s: Walking toward Travis (X: 270->440, Y: 1120->1080)
        # 36s - 48s: Split screen layout (Officer 1: X: 420, Y: 820; Officer 2: X: 540, Y: 1260) -> anchor X: 440, Y: 950
        # 48s - 65s: Escorting suspect to vehicle (X: 440->680, Y: 1150->1180)
        # 65s - 90s: Near patrol truck (X: 680->740, Y: 1180)
        def cop_pos(t: float):
            if t <= 24.0:
                return (280, 1120)
            elif t <= 36.0:
                p = (t - 24.0) / 12.0
                return (int(280 + p * 160), int(1120 - p * 40))
            elif t <= 48.0:
                return (450, 950)
            elif t <= 65.0:
                p = (t - 48.0) / 17.0
                return (int(450 + p * 230), int(1150 + p * 30))
            else:
                p = min(1.0, (t - 65.0) / 25.0)
                return (int(680 + p * 60), 1180)

        # SUSPECT: Travis in grey hoodie
        # 0s - 26s: Sitting on the sand (X: 530, Y: 1350)
        # 26s - 38s: Rising up (X: 530->550, Y: 1350->1270)
        # 38s - 55s: Standing with officers (X: 550, Y: 1320)
        # 55s - 90s: Walking with officer toward truck (X: 550->690, Y: 1320->1280)
        def suspect_pos(t: float):
            if t <= 26.0:
                return (530, 1350)
            elif t <= 38.0:
                p = (t - 26.0) / 12.0
                return (int(530 + p * 20), int(1350 - p * 80))
            elif t <= 55.0:
                return (550, 1320)
            else:
                p = min(1.0, (t - 55.0) / 35.0)
                return (int(550 + p * 140), int(1320 - p * 40))

        return {"COP": cop_pos, "SUSPECT": suspect_pos}

    elif "002" in clip_name:
        # vso_clip_002 (Boat ramp pursuit):
        # COP: Deputy running down the ramp to the airboat
        def cop_pos(t: float):
            if t <= 15.0:
                # Approaching ramp
                p = t / 15.0
                return (int(480 - p * 100), int(1150 + p * 40))
            elif t <= 45.0:
                # Getting on airboat at left
                p = (t - 15.0) / 30.0
                return (int(380 - p * 60), int(1190 + p * 30))
            else:
                # On boat in water
                p = min(1.0, (t - 45.0) / 60.0)
                return (int(320 + p * 60), 1220)

        # CITIZEN / BOATER: Boat owner at the ramp / truck
        def citizen_pos(t: float):
            if t <= 25.0:
                return (740, 1120)
            elif t <= 50.0:
                p = (t - 25.0) / 25.0
                return (int(740 - p * 100), int(1120 + p * 50))
            else:
                return (640, 1180)

        return {"COP": cop_pos, "CITIZEN": citizen_pos, "SUSPECT": citizen_pos}

    else:
        # vso_clip_003 (Night traffic stop):
        # SUSPECT: Standing by the car door on the left
        def suspect_pos(t: float):
            if t <= 25.0:
                p = t / 25.0
                return (int(350 + p * 40), 1100)
            elif t <= 45.0:
                p = (t - 25.0) / 20.0
                return (int(390 - p * 30), 1120)
            else:
                p = min(1.0, (t - 45.0) / 40.0)
                return (int(360 + p * 50), 1120)

        # COP: First-person bodycam officer anchor
        def cop_pos(t: float):
            return (540, 1440)

        return {"COP": cop_pos, "SUSPECT": suspect_pos}

def generate_motion_tracked_ass(events: list[dict], clip_name: str, duration: float, out_path: Path) -> Path:
    traj = get_clip_trajectory(clip_name, duration)
    
    # Colors matching viral police bodycam style:
    # COP -> Neon Cyan &H00FFFF00& or Vivid Red &H002222FF&
    # SUSPECT / BIKER -> Neon Green &H0033FF33& (identical to reference image)
    # CITIZEN / BOATER -> Bright Amber/Yellow &H0000E5FF&
    role_colors = {
        "COP": "&H002222FF&",       # Bright Red
        "SUSPECT": "&H0033FF33&",   # Neon Green (matches BIKER from user reference image)
        "BIKER": "&H0033FF33&",     # Neon Green
        "CITIZEN": "&H0000E5FF&"    # Bright Golden Yellow
    }

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # BorderStyle=3 gives the exact solid opaque black box around the text!
        "Style: TrackBox,Arial Black,64,&H00FFFFFF&,&H00000000,&H00000000,&H00000000,1,1,0,0,100,100,0,0,3,13,0,2,20,20,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for ev in events:
        role = ev["role"]
        st = ev["start"]
        ed = ev["end"]
        text = ev["text"]
        role_color = role_colors.get(role, "&H0033FF33&")
        tag_text = f"{role}:"

        # Lookup position trajectory
        pos_fn = traj.get(role, traj.get("COP"))
        x1, y1 = pos_fn(st)
        x2, y2 = pos_fn(ed)

        # Clamping within safe area to prevent clipping
        x1 = max(200, min(880, x1))
        x2 = max(200, min(880, x2))
        y1 = max(600, min(1500, y1))
        y2 = max(600, min(1500, y2))

        # If movement during event is significant (>12px), use ASS \move for continuous smooth tracking!
        dist = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
        if dist >= 12:
            motion_tag = f"\\move({x1},{y1},{x2},{y2})"
        else:
            motion_tag = f"\\pos({x1},{y1})"

        # Dialogue event: Top line is colored role tag with black box, bottom line is bold white text with black box
        dialogue = (
            f"Dialogue: 0,{ts_ass(st)},{ts_ass(ed)},TrackBox,,0,0,0,,"
            f"{{{motion_tag}}}"
            f"{{\\fs38\\c{role_color}}}{tag_text}\\N"
            f"{{\\fs64\\c&H00FFFFFF&}}{text}"
        )
        lines.append(dialogue)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path

def render_tracked_clip(folder_name: str, out_name="final_tracking_box.mp4") -> Path:
    folder = Path(folder_name).resolve()
    clip_file = folder / "clip.mp4"
    tagged_file = folder / "tagged_words.json"
    
    if not tagged_file.exists():
        raise FileNotFoundError(f"Missing {tagged_file}")

    words = json.loads(tagged_file.read_text(encoding="utf-8"))
    events = build_punchy_chunks(words)
    (folder / "tracking_events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    print(f"[{folder_name}] Created {len(events)} punchy dialogue chunks.")

    # Probe duration
    cap_info_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(clip_file)]
    res_dur = subprocess.run(cap_info_cmd, capture_output=True, text=True)
    duration = float(res_dur.stdout.strip()) if res_dur.stdout.strip() else 90.0

    ass_path = folder / "captions_tracking_box.ass"
    generate_motion_tracked_ass(events, folder_name, duration, ass_path)
    print(f"[{folder_name}] Generated ASS with character motion tracking: {ass_path}")

    out_file = folder / out_name
    ass_escaped = str(ass_path).replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'").replace(',', '\\,')
    vf = f"ass='{ass_escaped}'"

    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-i', str(clip_file),
        '-map', '0:v:0', '-map', '0:a:0',
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19',
        '-c:a', 'copy',
        '-movflags', '+faststart',
        str(out_file)
    ]

    print(f"[{folder_name}] Rendering {out_file.name} with FFmpeg (original lossless audio copy)...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {res.stderr}")

    print(f"[{folder_name}] SUCCESS! Saved: {out_file} (Size: {out_file.stat().st_size / (1024*1024):.2f} MB)")
    return out_file

if __name__ == "__main__":
    clips = ["vso_clip_001", "vso_clip_002", "vso_clip_003"]
    if len(sys.argv) > 1:
        clips = [sys.argv[1]]

    for c in clips:
        print(f"\n================ PROCESSING {c} ================")
        render_tracked_clip(c)
    print("\nALL CLIPS RENDERED SUCCESSFULLY WITH MOTION TRACKING BOX CAPTIONS!")
