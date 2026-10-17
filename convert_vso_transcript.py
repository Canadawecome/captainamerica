#!/usr/bin/env python3
import json, re
from pathlib import Path
from podcast_media import digest, probe
from podcast_contracts import Transcript, Word

def convert_sub(sub_file: Path, media_file: Path, out_file: Path):
    data = json.loads(sub_file.read_text(encoding="utf-8"))
    events = data.get("events", [])
    
    words = []
    all_raw_segs = []
    for ev in events:
        t_base = ev.get("tStartMs", 0)
        dur = ev.get("dDurationMs", 0)
        segs = ev.get("segs", [])
        for s in segs:
            txt = s.get("utf8", "").strip()
            if not txt or txt == "\n":
                continue
            offset = s.get("tOffsetMs", 0)
            st = round((t_base + offset) / 1000.0, 3)
            all_raw_segs.append((st, txt, (t_base + dur) / 1000.0))

    all_raw_segs.sort(key=lambda x: x[0])
    
    for i, (st, txt, ev_end) in enumerate(all_raw_segs):
        if i + 1 < len(all_raw_segs):
            next_st = all_raw_segs[i + 1][0]
            ed = min(ev_end, next_st)
        else:
            ed = ev_end
        if ed <= st:
            ed = round(st + 0.25, 3)
        words.append(Word(start=st, end=round(ed, 3), text=txt, speaker="speaker_1"))

    # Strictly ensure sorted & no start time inversions
    words.sort(key=lambda w: w.start)
    for i in range(1, len(words)):
        if words[i].start < words[i-1].start:
            words[i].start = words[i-1].start

    tx = Transcript(
        schema_version="podcast-v1",
        media_sha256=digest(media_file),
        language="en",
        timestamp_source="ASR_WORDS",
        words=words
    )
    out_file.write_text(tx.model_dump_json(indent=2), encoding="utf-8")
    print(f"Transcript converted! Total words: {len(words)}")
    return tx

if __name__ == "__main__":
    convert_sub(Path("vso_sub.en.json3"), Path("vso_source.mp4"), Path("vso_transcript.json"))
