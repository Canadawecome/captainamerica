# Podcast Forge v1.0 — Offline Verification

- Executed `PYTHONPATH=. pytest -q tests/test_podcast_v1.py` → **12 passed**.
- Real FFmpeg synthetic 112-second source and 68-second exported clip with AAC audio.
- Verified Opus proposed bounded source range and 70–100-second clip target.
- Verified score approval, FFprobe strict >65s, source mapping/rights, and rejection when meaning is distorted despite high score.
- Verified word-timed SRT/ASS, burned subtitles, 68s MP4 with an audio stream.
- Verified original AAC bitstream is unchanged in the default preserve render mode (`ffmpeg -map 0:a -c:a copy -f md5` check).
- Verified post-review approval becomes stale when transcript is changed.
- Verified long transcript chunking windows overlap and cover end of source.
- Verified GPT metadata is optional and produces editor-review drafts only.

**Test limitations:** Real speech diarization accuracy, speech emotion, semantic viral scoring, OpenAI and OpusClip provider calls, provider upload/poll/download, and rights review were NOT tested live. Synthetic test tones do not represent real podcast audio quality or semantic comprehension. No ElevenLabs was called.
