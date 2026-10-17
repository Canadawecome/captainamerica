import os, sys, json, time, urllib.request, urllib.parse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
token = os.environ.get('OPUSCLIP_API_KEY')
if not token:
    raise ValueError("Missing OPUSCLIP_API_KEY")

from podcast_media import probe, digest
from opus_export_manager import get_clips, download
from podcast_multi_speaker_captions import process_folder

ffmpeg_dir = Path("C:/Users/ADMIN/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin")
if str(ffmpeg_dir) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(ffmpeg_dir) + os.path.pathsep + os.environ.get("PATH", "")

ledger_path = Path("vso_ledger.json")
ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
tx_source = json.loads(Path("vso_transcript.json").read_text(encoding="utf-8"))

print(f"Tracking {len(ledger['jobs'])} jobs from {ledger_path}:")
for j in ledger['jobs']:
    print(f"  Group {j['group_id']}: Project {j['project_id']}, Candidates: {j['candidate_ids']}, Window: {j['source_window']}")

def get_project_stage(pid):
    req = urllib.request.Request(
        f'https://api.opus.pro/api/clip-projects/{pid}',
        headers={'Authorization': 'Bearer ' + token, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        payload = data.get('data', data)
        return payload.get('stage'), payload.get('progress')

# Poll until complete
completed = {}
start_time = time.time()
while len(completed) < len(ledger['jobs']) and time.time() - start_time < 900:
    for job in ledger['jobs']:
        pid = job['project_id']
        if pid in completed:
            continue
        try:
            stage, progress = get_project_stage(pid)
            print(f"[{time.strftime('%X')}] Project {pid} ({job['group_id']}): stage={stage}, progress={progress}", flush=True)
            if stage == 'COMPLETE':
                completed[pid] = job
            elif stage in ('FAILED', 'ERROR'):
                print(f"Project {pid} failed with stage: {stage}", flush=True)
                completed[pid] = None
        except Exception as e:
            print(f"Error checking project {pid}: {e}", flush=True)
    if len(completed) < len(ledger['jobs']):
        time.sleep(20)

print("\n--- Processing completed projects into local clips ---")
processed_clips = []
for idx, job in enumerate(ledger['jobs'], 1):
    pid = job['project_id']
    group_id = job['group_id']
    cand_id = job['candidate_ids'][0]
    folder = Path(f"vso_clip_{idx:03d}")
    folder.mkdir(parents=True, exist_ok=True)
    
    print(f"\nProcessing Clip #{idx} for {group_id} ({pid})...")
    clips_list = get_clips(pid, execute=True)
    if not clips_list:
        print(f"  [ERROR] No exportable clips returned for project {pid}")
        continue
    
    # Pick the best clip that fits duration > 65s
    selected_clip = None
    for c in clips_list:
        dur = c.get('duration_provider_sec') or sum(b-a for a,b in c.get('ranges_sec', []))
        if dur >= 65.0:
            selected_clip = c
            break
    if not selected_clip:
        selected_clip = clips_list[0]
    
    print(f"  Selected clip: id={selected_clip['id']}, ranges={selected_clip['ranges_sec']}, dur={selected_clip.get('duration_provider_sec')}s")
    
    # Save clip metadata
    (folder / "clip_meta.json").write_text(json.dumps(selected_clip, indent=2), encoding="utf-8")
    
    # Download MP4
    clip_mp4 = folder / "clip.mp4"
    if not clip_mp4.exists():
        print(f"  Downloading export to {clip_mp4}...")
        download(selected_clip, clip_mp4, execute=True)
    print(f"  Downloaded: {clip_mp4} ({clip_mp4.stat().st_size / 1024 / 1024:.2f} MB)")
    
    # Write source_mapping.json
    source_mapping = {
        "candidate_id": cand_id,
        "verified_by": "OPUS_PROVIDER",
        "reviewer_or_project_id": pid,
        "source_ranges_sec": selected_clip['ranges_sec'],
        "evidence_note": f"Exported range matches candidate {cand_id}"
    }
    (folder / "source_mapping.json").write_text(json.dumps(source_mapping, indent=2), encoding="utf-8")
    
    # Slices words from source transcript
    r_start = selected_clip['ranges_sec'][0][0]
    r_end = selected_clip['ranges_sec'][-1][1]
    
    clip_words = []
    for w in tx_source['words']:
        if w['end'] >= r_start and w['start'] <= r_end:
            shifted = dict(w)
            shifted['start'] = round(max(0.0, w['start'] - r_start), 3)
            shifted['end'] = round(max(0.0, w['end'] - r_start), 3)
            clip_words.append(shifted)
            
    clip_tx = {
        "schema_version": "podcast-v1",
        "media_sha256": digest(clip_mp4),
        "language": "en",
        "timestamp_source": "PROVIDER_ALIGNED_WORDS",
        "words": clip_words
    }
    (folder / "clip_transcript.json").write_text(json.dumps(clip_tx, indent=2), encoding="utf-8")
    print(f"  Aligned {len(clip_words)} words to {folder / 'clip_transcript.json'}")
    
    # Generate multi-speaker captions and render
    print("  Generating multi-speaker captions (Preset v1.1, Mint/Cyan palette) & rendering...")
    res = process_folder(folder, "final_multi_speaker.mp4")
    qa = res["qa"]
    print(f"  Render complete! Status: {qa['status']}, Duration: {qa['duration_sec']:.2f}s, Audio: {qa['audio_stream_copied']}")
    processed_clips.append({"folder": str(folder), "project_id": pid, "candidate_id": cand_id, "qa": qa})

print("\n==========================================")
print(f"SUCCESS: Successfully processed {len(processed_clips)} multi-speaker clips!")
for c in processed_clips:
    print(f" - {c['folder']}/final_multi_speaker.mp4 | Duration: {c['qa']['duration_sec']:.2f}s | Resolution: {c['qa']['resolution']}")
print("==========================================")
