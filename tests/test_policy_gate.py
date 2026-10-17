import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from policy_gate import evaluate_policy


class PolicyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preset = json.loads((ROOT / "podcast_sortformer_preset_v12.json").read_text(encoding="utf-8"))
        cls.job = json.loads((ROOT / "examples" / "approved_clip_status.json").read_text(encoding="utf-8"))

    def evaluate(self, preset=None, job=None):
        return evaluate_policy(preset or copy.deepcopy(self.preset), job or copy.deepcopy(self.job))

    def permitted_preset(self):
        p = copy.deepcopy(self.preset)
        model = p["diarization"]["model_id"]
        p["diarization"]["model_revision"] = "verified_commit_example_for_unit_tests"
        p["licensing"]["approved_model_weights"] = [model]
        p["licensing"]["verified_license_evidence"] = {model: "example_written_license_evidence_in_unit_test"}
        return p

    def test_default_commercial_blocked_due_to_noncommercial_model(self):
        self.assertEqual(self.evaluate()["status"], "BLOCKED_LICENSE")

    def test_explicit_model_license_flag_cannot_skip_revision_pin(self):
        p = self.permitted_preset()
        p["diarization"]["model_revision"] = "PIN_EXACT_COMMIT_BEFORE_USE"
        self.assertEqual(self.evaluate(preset=p)["status"], "MODEL_REVISION_UNPINNED")

    def test_mock_approved_policy_passes(self):
        self.assertEqual(self.evaluate(preset=self.permitted_preset())["status"], "POLICY_PASS")

    def test_5_speakers_blocked(self):
        j = copy.deepcopy(self.job)
        j["distinct_speakers"] = 5
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "UNSUPPORTED_SPEAKER_COUNT")

    def test_clip_not_approved_blocked(self):
        j = copy.deepcopy(self.job)
        j["gpt_postcut_status"] = "RECUT"
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "CLIP_UNAPPROVED")

    def test_rights_missing_blocked(self):
        j = copy.deepcopy(self.job)
        j["rights_verified"] = False
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "RIGHTS_UNVERIFIED")

    def test_duration_default_optional(self):
        j = copy.deepcopy(self.job)
        j["duration_sec_ffprobe"] = 43.0
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "POLICY_PASS")

    def test_duration_threshold_exact_65_fails_when_enabled(self):
        p = self.permitted_preset()
        p["duration_policy"]["monetization_gt_65s"] = True
        j = copy.deepcopy(self.job)
        j["duration_sec_ffprobe"] = 65.0
        self.assertEqual(self.evaluate(preset=p, job=j)["status"], "DURATION_FAIL")
        j["duration_sec_ffprobe"] = 65.01
        self.assertEqual(self.evaluate(preset=p, job=j)["status"], "POLICY_PASS")

    def test_elevenlabs_must_remain_disabled(self):
        p = self.permitted_preset()
        p["voiceover"]["elevenlabs_enabled"] = True
        self.assertEqual(self.evaluate(preset=p)["status"], "PODCAST_VOICEOVER_FORBIDDEN")

    def test_final_audio_policy_mismatch(self):
        j = copy.deepcopy(self.job)
        j["source_audio_policy"] = "GENERATED_VOICE"
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "AUDIO_POLICY_MISMATCH")

    def test_missing_timeline_revision_blocked(self):
        j = copy.deepcopy(self.job)
        j["timeline_revision"] = ""
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "TIMELINE_NOT_LOCKED")

    def test_unknown_speaker_count_blocked(self):
        j = copy.deepcopy(self.job)
        j["distinct_speakers"] = None
        self.assertEqual(self.evaluate(preset=self.permitted_preset(), job=j)["status"], "UNKNOWN_SPEAKER_COUNT")


if __name__ == "__main__":
    unittest.main()
