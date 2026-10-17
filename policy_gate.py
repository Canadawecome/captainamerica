"""Podcast Forge v1.2: stand-alone policy preflight reference.

Does NOT download/run NeMo or WhisperX, verify footage rights, measure an MP4,
verify a legal agreement, analyze diarization, or render captions.
The production orchestrator must supply independently verified job fields.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


NONCOMMERCIAL_WEIGHT_MODELS = {"nvidia/diar_sortformer_4spk-v1"}
PODCAST_NATIVE_AUDIO = "PRESERVE_FINAL_NATIVE_AUDIO"


def evaluate_policy(preset: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed single-result checks in dependency order, no side effects."""
    def block(status: str, reason: str) -> dict[str, Any]:
        return {"allowed": False, "status": status, "reason": reason}

    if preset.get("product") != "PODCAST_FORGE_NATIVE_ENGLISH":
        return block("INVALID_PRODUCT", "Preset is not the podcast profile")
    if preset.get("voiceover", {}).get("elevenlabs_enabled") is not False or preset.get("voiceover", {}).get("tts_enabled") is not False:
        return block("PODCAST_VOICEOVER_FORBIDDEN", "Podcast must preserve native source speech")
    if preset.get("audio_policy") != PODCAST_NATIVE_AUDIO or job.get("source_audio_policy") != PODCAST_NATIVE_AUDIO:
        return block("AUDIO_POLICY_MISMATCH", "Podcast master audio must remain native")
    if not (preset.get("selection", {}).get("rights_verified") is True or job.get("rights_verified") is True):
        return block("RIGHTS_UNVERIFIED", "Rights must be verified by a real operator")
    if job.get("gpt_postcut_status") != "APPROVED":
        return block("CLIP_UNAPPROVED", "GPT pass 2 has not approved the final clip")
    if job.get("timeline_locked") is not True or not str(job.get("timeline_revision", "")).startswith("sha256:"):
        return block("TIMELINE_NOT_LOCKED", "Require locked timeline revision")

    duration = job.get("duration_sec_ffprobe")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        return block("INVALID_DURATION", "Duration must be measured from real media by ffprobe upstream")
    if not (0 < float(duration) < float("inf")):
        return block("INVALID_DURATION", "Invalid ffprobe media duration")
    duration_conf = preset.get("duration_policy", {})
    if duration_conf.get("monetization_gt_65s") and float(duration) <= float(duration_conf.get("strict_threshold_sec", 65)):
        return block("DURATION_FAIL", "Podcast campaign requires duration strictly greater than threshold")

    diar = preset.get("diarization", {})
    model_id = diar.get("model_id")
    if diar.get("primary_provider") != "nemo_sortformer" and not diar.get("fallback_provider"):
        return block("NO_DIARIZER_CONFIGURED", "Diarization provider required")

    licensing = preset.get("licensing", {})
    is_commercial = licensing.get("commercial_mode") is True
    approval_list = licensing.get("approved_model_weights", [])
    evidence = licensing.get("verified_license_evidence", {})
    if is_commercial:
        if model_id not in approval_list or not isinstance(evidence.get(model_id), str) or not evidence.get(model_id, "").strip():
            return block("BLOCKED_LICENSE", "Model weights require documented commercial authorization before inference")
    if model_id in NONCOMMERCIAL_WEIGHT_MODELS and is_commercial and not licensing.get("block_before_model_download_or_inference", True):
        return block("UNSAFE_LICENSE_CONFIG", "Cannot disable licensed checkpoint preflight")

    revision = diar.get("model_revision", "")
    if not isinstance(revision, str) or not revision.strip() or revision.startswith("PIN_"):
        return block("MODEL_REVISION_UNPINNED", "Pin exact reviewed checkpoint commit/revision")

    speaker_count = job.get("distinct_speakers")
    if isinstance(speaker_count, bool) or not isinstance(speaker_count, int) or speaker_count < 1:
        return block("UNKNOWN_SPEAKER_COUNT", "Count must be verified or routed to review")
    max_speakers = diar.get("max_distinct_speakers", 4)
    if speaker_count > max_speakers:
        return block("UNSUPPORTED_SPEAKER_COUNT", "Use an explicitly approved >4-speaker-capable fallback")

    return {"allowed": True, "status": "POLICY_PASS", "reason": "Policy metadata passed; no model, media or licensing evidence independently verified"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    preset = json.loads(Path(args.preset).read_text(encoding="utf-8"))
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    result = evaluate_policy(preset, job)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["allowed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
