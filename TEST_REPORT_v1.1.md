# Podcast Forge v1.1 — Offline Tests · 2026-10-17

Command: `PYTHONPATH=.:tests python -m pytest -q tests/test_podcast_v1.py tests/test_opus_expert_shared.py tests/test_podcast_v11_expert.py`

**27/27 passed.** Coverage: legacy real FFmpeg podcast render with native AAC bitstream, 65s strict gate, source hash and mapping verification, speaker captions, content-only Opus prompts, grouped source windows, quote-aware hook validation, semantic recut proposal, per-project submission budget guard, Get Clips timeRanges ms→s conversion and group match, Opus transcript normalization, dry-run and safe export URL handling, audio diagnostics.

Not tested live: actual OpenAI/Opus auth and API responses on user's account, face tracking, webhook polling, transcript accuracy on real voices.
