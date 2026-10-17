# Changelog — Podcast Forge Multi-Speaker Captions 1.1 → 1.2

- `pyannote_community_1` removed as automatic primary. NVIDIA NeMo Sortformer offline `nvidia/diar_sortformer_4spk-v1` is the preferred speaker-diarization provider **only after model weights license approval**.
- WhisperX remains the sole ASR/word alignment provider; Sortformer output is multi-label speaker activity and must retain overlapping intervals.
- Added explicit 4 distinct-speaker capacity check, conservative UNKNOWN behavior, optional approved alternative for >4 or restricted weights.
- Added non-commercial license guard for the offline model (`CC BY-NC 4.0`), separate from NeMo framework licensing.
- Added chunk-local to clip-global speaker reconciliation requirements and cross-talk transcription review.
- Added explicit LR-ASD/TalkNet audiovisual identity evidence for face-attached captions; no voice-to-face inference from shot alone.
- Kept `SPEAKER_COLOR`, `CHARACTER_TRACK`, `SMART_HYBRID` (default), existing fixed caption styling 56px/y=.78, original audio intact and the existing GPT→OpusClip→GPT selection pipeline.
- Kept podcast duration gate >65 seconds **optional** and ElevenLabs disabled.
- Added executable **policy-only** reference and unit tests. No ML engine, lip sync, caption renderer or integration was implemented by this patch.
