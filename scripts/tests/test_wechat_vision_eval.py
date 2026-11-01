"""Offline safety, regression and provider-circuit evidence; no SDK import or key."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from integrations.wechat.model import ConnectorError
from integrations.wechat.vision_eval import FREE_MODELS, SCENES, compare_reports, evaluate, parse_object, parse_provider_object, same_typed_value
from integrations.wechat.provider_profile import load_profile, store_profile


class ParserTests(unittest.TestCase):
    def test_plain_and_single_fence_have_distinct_evidence(self):
        self.assertEqual(parse_object('{"code":"7426"}'), ({"code": "7426"}, False))
        self.assertEqual(parse_object('```json\n{"code":"7426"}\n```'), ({"code": "7426"}, True))

    def test_prose_duplicate_trailing_multiple_and_nonfinite_are_rejected(self):
        for value in ('Explanation: {"x":1}', '{"x":1} trailing', '{"x":1,"x":2}',
                      '```json\n{"x":1}\n```\nExplanation', '{"x":NaN}', '[]',
                      '```json\n{}\n```\n```json\n{}\n```'):
            with self.subTest(value=value), self.assertRaises(ConnectorError):
                parse_object(value)

    def test_exact_typed_values_preserve_duplicates_and_missing_information(self):
        self.assertFalse(same_typed_value({"A": True}, {"A": 1}))
        self.assertFalse(same_typed_value({"deadline": "next Monday"}, {"deadline": None}))
        self.assertFalse(same_typed_value({"messages": ["收到"]}, {"messages": ["收到", "收到"]}))
        self.assertFalse(same_typed_value({"x": 1, "extra": "data"}, {"x": 1}))

    def test_known_reasoning_envelope_returns_answer_only_and_provenance(self):
        text = '<think>untrusted reasoning {"wrong":true}</think><answer><|begin_of_box|>{"code":"7426"}<|end_of_box|></answer>'
        value, flags = parse_provider_object("glm-4.1v-thinking-flash", text)
        self.assertEqual(value, {"code": "7426"})
        self.assertTrue(flags["reasoning_envelope"])
        self.assertNotIn("untrusted reasoning", json.dumps([value, flags]))
        with self.assertRaises(ConnectorError):
            parse_provider_object("glm-4v-flash", text)

    def test_partial_or_extra_envelopes_refused(self):
        for text in ('<think>unfinished {"code":"7426"}', '<answer>{}</answer> trailing',
                     '<think>one</think><think>two</think>{}', '<|begin_of_box|>{}',
                     '<answer>{}</answer><answer>{}</answer>'):
            with self.subTest(text=text), self.assertRaises(ConnectorError):
                parse_provider_object("glm-4.1v-thinking-flash", text)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # No renderer dependency: transport is injected, these bytes never leave the test.
        manifest = {"kind": "classmatter.synthetic-vision-fixtures.v1", "images": {}}
        for scene in SCENES:
            raw = b"\x89PNG\r\n\x1a\n" + scene.name.encode("ascii")
            (self.root / (scene.name + ".png")).write_bytes(raw)
            manifest["images"][scene.name] = hashlib.sha256(raw).hexdigest()
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.output = self.root / "result.json"

    def test_eight_scene_success_keeps_strict_json_and_normalized_separate(self):
        calls = []
        def request(model, messages):
            index = len(calls)
            calls.append(model)
            return {"choices": [{"finish_reason": "stop", "message": {
                "content": '```json\n' + json.dumps(SCENES[index].expected) + '\n```'}}],
                    "usage": {"total_tokens": 100, "unexpected": "not-exported"}}
        report = evaluate(self.root, self.output, request, models=(FREE_MODELS[0],), pause=lambda _: None)
        self.assertEqual(report["summary"][FREE_MODELS[0]], {"passed": 8, "failed": 0, "skipped": 0})
        self.assertTrue(all(not r["strict_json"] and r["normalized_json"] for r in report["results"]))
        self.assertFalse(report["real_wechat_tested"])
        self.assertNotIn("unexpected", self.output.read_text())

    def test_provider_failure_opens_circuit_without_exporting_secret_error(self):
        class QuotaError(Exception):
            status_code = 429
            body = {"error": {"code": "1305", "message": "must-not-export-private-detail"}}
        calls = []
        def request(model, messages):
            calls.append(model)
            raise QuotaError("must-not-export-private-detail")
        report = evaluate(self.root, self.output, request, models=FREE_MODELS, pause=lambda _: None)
        self.assertEqual(len(calls), 3)
        self.assertEqual(report["requests"], 3)
        self.assertTrue(all(s["failed"] == 1 and s["skipped"] == 7 for s in report["summary"].values()))
        self.assertNotIn("must-not-export", self.output.read_text())

    def test_paid_model_refused_before_any_transport(self):
        def forbidden(*_):
            self.fail("network should not be called")
        with self.assertRaisesRegex(ConnectorError, "free_model_allowlist_required"):
            evaluate(self.root, self.output, forbidden, models=("glm-4.6v",))

    def test_fixture_drift_refused_before_any_transport(self):
        (self.root / "digits.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ConnectorError, "fixture_digest_mismatch"):
            evaluate(self.root, self.output, lambda *_: self.fail("no transport"))

    def test_quality_failure_does_not_skip_remaining_cases(self):
        def request(*_):
            return {"choices": [{"finish_reason": "stop", "message": {"content": '{"wrong":true}'}}]}
        report = evaluate(self.root, self.output, request, models=(FREE_MODELS[0],), pause=lambda _: None)
        self.assertEqual(report["summary"][FREE_MODELS[0]]["failed"], 8)
        self.assertEqual(report["summary"][FREE_MODELS[0]]["skipped"], 0)

    def test_regression_comparison_requires_same_cases_and_images(self):
        before = {"kind": "classmatter.synthetic-vision-evidence.v1", "case_digest": "synthetic-case",
                  "fixture_digests": {"digits": "synthetic-image"}, "results": [
                      {"model": FREE_MODELS[0], "scene": s.name, "status": "passed"} for s in SCENES]}
        after = json.loads(json.dumps(before))
        after["results"][0]["status"] = "quality-failed"
        self.assertEqual(len(compare_reports(before, after)["regressions"]), 1)
        after["case_digest"] = "changed"
        with self.assertRaisesRegex(ConnectorError, "incomparable_evidence"):
            compare_reports(before, after)

    def test_truncated_but_valid_json_cannot_pass(self):
        def request(*_):
            return {"choices": [{"finish_reason": "length", "message": {"content": '{"code":"7426"}'}}]}
        report = evaluate(self.root, self.output, request, models=(FREE_MODELS[0],), pause=lambda _: None)
        self.assertEqual(report["summary"][FREE_MODELS[0]]["passed"], 0)

    def test_comparison_rejects_missing_cases_and_all_skipped(self):
        before = {"kind": "classmatter.synthetic-vision-evidence.v1", "case_digest": "synthetic-case",
                  "fixture_digests": {}, "results": [
                      {"model": FREE_MODELS[0], "scene": s.name, "status": "passed"} for s in SCENES]}
        after = json.loads(json.dumps(before))
        after["results"].pop()
        with self.assertRaisesRegex(ConnectorError, "incomplete_evidence_rows"):
            compare_reports(before, after)
        after = json.loads(json.dumps(before))
        for row in after["results"]:
            row["status"] = "skipped-provider-unavailable"
        with self.assertRaisesRegex(ConnectorError, "no_comparable_evidence"):
            compare_reports(before, after)


class ProfileTests(unittest.TestCase):
    @staticmethod
    def codec(raw, *, decrypt=False):
        # Test-only stand-in. Production always delegates Windows current-user DPAPI.
        return raw[::-1]

    def test_profile_roundtrip_preserves_free_model_and_keeps_key_out_of_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.dpapi"
            store_profile("synthetic-placeholder-not-a-key", FREE_MODELS[1], path, codec=self.codec)
            self.assertNotIn(b"synthetic-placeholder-not-a-key", path.read_bytes())
            value = load_profile(path, codec=self.codec)
            self.assertEqual(value["model"], FREE_MODELS[1])
            self.assertEqual(value["api_key"], "synthetic-placeholder-not-a-key")

    def test_paid_model_or_invalid_key_does_not_modify_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.dpapi"
            for key, model in [("synthetic-placeholder", "glm-4.6v"), ("bad key", FREE_MODELS[0])]:
                with self.assertRaises(ConnectorError):
                    store_profile(key, model, path, codec=self.codec)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
