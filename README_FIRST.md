# Local Podcast Forge v1.1 — OpusClip Expert Cut

**Nguồn:** Podcast tiếng Anh Mỹ/Anh, giữ giọng nói thật, không ElevenLabs hoặc ASMR separation.

**Đọc:** `SPEC_Local_Podcast_Forge_v1.1_OPUS_EXPERT_CUT.md` làm SPEC chính. Bản v1.0 cất trong `legacy_docs/`.

**Module:** `podcast_director.py` (full phrase hook + close-of-thought review + bundling), `podcast_opus_submit.py` (batch max 8 unless explicit override), `opus_expert_core.py` (content-only prompts, curation vs render), `opus_export_manager.py` (Get Clips/timeRanges/download, optional), `opus_transcript_manager.py` (timed words từ Opus), `podcast_semantic_recut_v11.py` (source transcript boundaries), `opus_recut_engine.py` (local recut, always re-review), `opus_audio_qc.py` (audio diagnostics), `podcast_render.py` (native audio + English captions), `podcast_gpt.py` (transcript chunk overlap + GPT passes).

```bash
python -m pip install -r requirements.txt
PYTHONPATH=.:tests pytest -q tests/test_podcast_v1.py tests/test_podcast_v11_expert.py tests/test_opus_expert_shared.py
```

**Cảnh báo:** Không có one-click app/cloud polling production; hai API thực chưa thử live; active speaker tracking trong Opus là tùy cấu hình/provider, không có model face tracking local. Nội dung bên thứ ba phải được cho phép sử dụng.
