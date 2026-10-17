# Podcast Forge v1.2 — Policy Gate Test Report

**Run date:** 2026-10-17  
**Scope:** pure Python policy checks ONLY; no neural model, GPU, actual video, cloud API or caption renderer invoked.

## Results

- Command: `python -m unittest discover -s tests -v`
- **12/12 PASS** (local execution)
- Baseline commercial preset intentionally yields `BLOCKED_LICENSE` for `nvidia/diar_sortformer_4spk-v1` until verified usage rights are documented and model revision pinned.

Cases tested: default noncommercial model weights block in commercial mode, rights guard, GPT postcut approval, optional >65 seconds threshold, exact 65.00 case, 5 speakers guard, model version pinning, ElevenLabs disabled, native audio policy, timeline lock, missing speaker count and synthetic operator-declared approval path.

## Not tested / not built

- NeMo Sortformer inference / DER / overlap speaker quality
- WhisperX transcription or alignment accuracy
- Long-file chunk reconciliation against real audio
- Speaker-to-face matching with LR-ASD/TalkNet
- Smart Hybrid tracking renderer and caption legibility on a real MP4
- Real OpusClip/GPT selection integrations
- Validity/authenticity of contractual commercial model-weight rights (requires legal/operator review)

This report is **not** a claim the complete Podcast Forge has been implemented.
