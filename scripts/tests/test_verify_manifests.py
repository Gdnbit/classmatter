from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_manifests import (
    ManifestError,
    validate_eval_meta,
    validate_gate_graph,
    validate_task_graph,
    verify_self,
)


class RepoCopyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        for relative in (".ai/gates", "evals/class-os-v1", "docs/specs/class-os-v1"):
            source = REPO_ROOT / relative
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def mutate(self, relative: str, old: str, new: str, count: int = 1) -> None:
        path = self.repo / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"mutation anchor missing in {relative}")
        path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")


class SelfTests(unittest.TestCase):
    def test_self_check_passes(self) -> None:
        summary = verify_self(REPO_ROOT)
        self.assertEqual(summary["release"], "class-os-r1")
        self.assertTrue(summary["duplicate_key_guard"])


class EvalMetaTests(RepoCopyTestCase):
    def test_baseline_passes_and_counts_are_explicit(self) -> None:
        summary = validate_eval_meta(self.repo)
        self.assertEqual(summary["required_eval_count"], 147)
        self.assertEqual(summary["executable_spec_count"], 82)
        self.assertEqual(summary["executable_container_count"], 23)

    def test_duplicate_eval_id_fails(self) -> None:
        path = self.repo / ".ai/gates/release-1-evals.yaml"
        text = path.read_text(encoding="utf-8")
        first_entry = next(line for line in text.splitlines() if line.startswith("  - {eval_id:"))
        path.write_text(text.replace(first_entry, first_entry + "\n" + first_entry, 1), encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "duplicate eval_id"):
            validate_eval_meta(self.repo)

    def test_unknown_required_before_fails(self) -> None:
        self.mutate(
            ".ai/gates/release-1-evals.yaml",
            "required_before: first-feature-task",
            "required_before: invented-stage",
        )
        with self.assertRaisesRegex(ManifestError, "required_before"):
            validate_eval_meta(self.repo)

    def test_unknown_eval_entry_key_fails(self) -> None:
        self.mutate(
            ".ai/gates/release-1-evals.yaml",
            "evidence: null}",
            "evidence: null, surprise: true}",
        )
        with self.assertRaisesRegex(ManifestError, "unknown keys"):
            validate_eval_meta(self.repo)

    def test_maturity_drift_fails(self) -> None:
        self.mutate(
            ".ai/gates/release-1-evals.yaml",
            "spec_status: executable-spec",
            "spec_status: catalogued",
        )
        with self.assertRaisesRegex(ManifestError, "maturity"):
            validate_eval_meta(self.repo)

    def test_missing_executable_field_fails(self) -> None:
        self.mutate(
            "evals/class-os-v1/executable/release-1-p0.md",
            "- cleanup: 删除合成 workspace；确认无对象/队列残留。\n",
            "",
        )
        with self.assertRaisesRegex(ManifestError, "cleanup"):
            validate_eval_meta(self.repo)

    def test_duplicate_yaml_mapping_key_fails(self) -> None:
        path = self.repo / ".ai/gates/release-1-evals.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "\nrelease: duplicate\n", encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "duplicate YAML key"):
            validate_eval_meta(self.repo)


class GateGraphTests(RepoCopyTestCase):
    def test_baseline_gate_graph_passes(self) -> None:
        summary = validate_gate_graph(self.repo)
        self.assertEqual(summary["requirement_count"], 107)
        self.assertEqual(summary["task_count"], 94)
        self.assertEqual(summary["required_eval_count"], 147)

    def test_unknown_task_eval_reference_fails(self) -> None:
        self.mutate(
            ".ai/gates/release-1-task-definitions.yaml",
            "E-PRV-005",
            "E-NOPE-999",
        )
        with self.assertRaisesRegex(ManifestError, "unknown eval reference"):
            validate_gate_graph(self.repo)

    def test_requirement_cannot_be_included_and_excluded(self) -> None:
        self.mutate(
            ".ai/gates/release-1-requirements.yaml",
            "excluded:\n",
            "excluded:\n  FR-PLT-001: duplicate_classification\n",
        )
        with self.assertRaisesRegex(ManifestError, "both included and excluded"):
            validate_gate_graph(self.repo)

    def test_unknown_root_key_fails(self) -> None:
        path = self.repo / ".ai/gates/release-1-requirements.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "\nunexpected_root: true\n", encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "unknown keys"):
            validate_gate_graph(self.repo)


class TaskGraphTests(RepoCopyTestCase):
    def test_before_feature_diagnostic_reports_exact_dependencies_without_authority(self) -> None:
        summary = validate_task_graph(self.repo)
        expected = [
            "T-REVAL-001", "T-REVAL-002", "T-REVAL-012",
            "T-REVAL-019", "T-REVAL-020", "T-RGOV-001", "T-RGOV-004",
            "T-RGOV-006", "T-RSPK-001", "T-RSPK-003",
        ]
        expected = sorted([*expected, "T-RGOV-002", "T-RGOV-003"])
        self.assertEqual(summary["before_feature_task_closure"], expected)
        self.assertEqual(summary["before_feature_task_incomplete_tasks"], expected)
        self.assertFalse(summary["before_feature_tasks_complete"])
        self.assertEqual(summary["before_feature_required_eval_ids"],
                         ["E-ARCH-002", "E-GATE-001", "E-GATE-002", "E-TASK-001"])
        self.assertEqual(summary["before_feature_catalogued_eval_ids"],
                         summary["before_feature_required_eval_ids"])
        self.assertFalse(summary["authorization"])

    def test_unknown_before_feature_root_is_rejected_by_task_diagnostic(self) -> None:
        self.mutate(".ai/gates/release-1-release-gates.yaml",
                    "required_task_roots: [T-RGOV-004,", "required_task_roots: [T-RNOPE-999,")
        with self.assertRaisesRegex(ManifestError, "unknown task roots"):
            validate_task_graph(self.repo)

    def test_unknown_before_feature_selector_label_is_rejected(self) -> None:
        self.mutate(".ai/gates/release-1-release-gates.yaml",
                    "include_required_before: [first-feature-task]",
                    "include_required_before: [invented-stage]")
        with self.assertRaisesRegex(ManifestError, "selector"):
            validate_task_graph(self.repo)

    def test_before_feature_selector_cannot_ignore_unknown_labels(self) -> None:
        self.mutate(".ai/gates/release-1-release-gates.yaml",
                    "unknown_required_before: fail", "unknown_required_before: ignore")
        with self.assertRaisesRegex(ManifestError, "selector"):
            validate_task_graph(self.repo)

    def test_baseline_hash_dag_closure_and_three_state_summary(self) -> None:
        summary = validate_task_graph(self.repo)
        self.assertEqual(summary["task_count"], 94)
        self.assertEqual(summary["source_row_count"], 94)
        self.assertEqual(summary["implemented_green_count"], 0)
        self.assertEqual(summary["release_candidate_closure_count"], 91)
        self.assertEqual(summary["pilot_readiness_closure_count"], 93)
        self.assertEqual(
            summary["release_candidate_omitted_tasks"],
            ["T-RREL-001", "T-RREL-002", "T-RREL-003"],
        )
        self.assertEqual(summary["pilot_readiness_omitted_tasks"], ["T-RREL-003"])
        self.assertFalse(summary["release_candidate_tasks_complete"])
        self.assertFalse(summary["pilot_readiness_tasks_complete"])

    def test_markdown_row_hash_mutation_fails(self) -> None:
        self.mutate(
            "docs/specs/class-os-v1/release-1-atomic-tasks.md",
            "指定数据控制、处理、安全、支持和审批责任人",
            "指定数据控制、处理、安全、支持和审批责任人（篡改）",
        )
        with self.assertRaisesRegex(ManifestError, "task body hash mismatch"):
            validate_task_graph(self.repo)

    def test_dependency_cycle_fails(self) -> None:
        self.mutate(
            ".ai/gates/release-1-task-definitions.yaml",
            "task_id: T-RGOV-001\n    source_line: 19\n    effort_days: 1\n    goal: \"指定数据控制、处理、安全、支持和审批责任人\"\n    depends_on: []",
            "task_id: T-RGOV-001\n    source_line: 19\n    effort_days: 1\n    goal: \"指定数据控制、处理、安全、支持和审批责任人\"\n    depends_on: [T-RGOV-004]",
        )
        with self.assertRaisesRegex(ManifestError, "cycle"):
            validate_task_graph(self.repo)

    def test_dependency_range_expression_is_not_expanded(self) -> None:
        self.mutate(
            ".ai/gates/release-1-task-definitions.yaml",
            "depends_on: [T-RGOV-001]",
            "depends_on: [\"T-RGOV-001—004\"]",
        )
        with self.assertRaisesRegex(ManifestError, "exact IDs"):
            validate_task_graph(self.repo)

    def test_pinned_definition_detects_deleted_dependency(self) -> None:
        definition = self.repo / ".ai/gates/release-1-task-definitions.yaml"
        digest = hashlib.sha256(definition.read_bytes()).hexdigest()
        self.mutate(
            ".ai/gates/release-1-tasks.yaml",
            "definition_sha256: null",
            f"definition_sha256: {digest}",
        )
        validate_task_graph(self.repo)
        self.mutate(
            ".ai/gates/release-1-task-definitions.yaml",
            "depends_on: [T-RGOV-001]",
            "depends_on: []",
        )
        with self.assertRaisesRegex(ManifestError, "pinned task definition digest"):
            validate_task_graph(self.repo)

    def test_complete_task_requires_complete_transitive_dependency(self) -> None:
        self.mutate(
            ".ai/gates/release-1-tasks.yaml",
            "{task_id: T-RGOV-002, status: planned, target_commit: null, evidence: null}",
            "{task_id: T-RGOV-002, status: complete, target_commit: 0123456789abcdef0123456789abcdef01234567, evidence: {artifact_id: synthetic-task-evidence}}",
        )
        with self.assertRaisesRegex(ManifestError, "dependency T-RGOV-001 is not complete"):
            validate_task_graph(self.repo)

    def test_fake_implemented_green_without_signed_state_fails(self) -> None:
        self.mutate(
            ".ai/gates/release-1-eval-state.yaml",
            "overrides: []",
            "overrides:\n  - {eval_id: E-AUTH-001, status: implemented-green, evidence: null}",
        )
        with self.assertRaisesRegex(ManifestError, "implemented-green"):
            validate_task_graph(self.repo)

    def test_field_complete_but_unverified_task_evidence_fails_closed(self) -> None:
        definition = self.repo / ".ai/gates/release-1-task-definitions.yaml"
        state_path = self.repo / ".ai/gates/release-1-tasks.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        commit = "0123456789abcdef0123456789abcdef01234567"
        state.update(
            {
                "definition_sha256": hashlib.sha256(definition.read_bytes()).hexdigest(),
                "definition_bundle_sha256": "1" * 64,
                "target_release_digest": "2" * 64,
                "target_commit": commit,
                "state_transition_artifact": {"artifact_uri": "unsigned://transition"},
            }
        )
        state["tasks"][0].update(
            {
                "status": "complete",
                "target_commit": commit,
                "evidence": {
                    "artifact_uri": "unsigned://task-evidence",
                    "sha256": "3" * 64,
                    "produced_at": "2026-09-22T00:00:00Z",
                    "task_id": "T-RGOV-001",
                    "task_definition_sha256": state["definition_sha256"],
                    "task_body_sha256": "4" * 64,
                    "target_release_digest": state["target_release_digest"],
                    "target_commit": commit,
                    "verifier_digest": "5" * 64,
                    "dsse_envelope_uri": "unsigned://envelope",
                },
            }
        )
        state_path.write_text(yaml.safe_dump(state, sort_keys=False), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ManifestError, "verified evidence adapter"):
            validate_task_graph(self.repo)

    def test_field_complete_but_unverified_eval_evidence_fails_closed(self) -> None:
        definition = self.repo / ".ai/gates/release-1-evals.yaml"
        state_path = self.repo / ".ai/gates/release-1-eval-state.yaml"
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        commit = "0123456789abcdef0123456789abcdef01234567"
        release_digest = "2" * 64
        definition_digest = hashlib.sha256(definition.read_bytes()).hexdigest()
        state.update(
            {
                "definition_sha256": definition_digest,
                "target_release_digest": release_digest,
                "target_commit": commit,
                "state_transition_artifact": {"artifact_uri": "unsigned://transition"},
                "overrides": [
                    {
                        "eval_id": "E-AUTH-001",
                        "status": "implemented-green",
                        "evidence": {
                            "artifact_uri": "unsigned://eval-evidence",
                            "sha256": "3" * 64,
                            "produced_at": "2026-09-22T00:00:00Z",
                            "eval_id": "E-AUTH-001",
                            "eval_definition_sha256": definition_digest,
                            "runner_digest": "4" * 64,
                            "target_release_digest": release_digest,
                            "target_commit": commit,
                            "environment_digest": "5" * 64,
                            "dsse_envelope_uri": "unsigned://envelope",
                        },
                    }
                ],
            }
        )
        state_path.write_text(yaml.safe_dump(state, sort_keys=False), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ManifestError, "verified evidence adapter"):
            validate_task_graph(self.repo)

    def test_state_manifest_identity_must_match_runner_input(self) -> None:
        self.mutate(
            ".ai/gates/release-1-tasks.yaml",
            "definition_manifest: .ai/gates/release-1-task-definitions.yaml",
            "definition_manifest: attacker.yaml",
        )
        with self.assertRaisesRegex(ManifestError, "definition_manifest"):
            validate_task_graph(self.repo)

    def test_malformed_task_id_is_manifest_error(self) -> None:
        self.mutate(
            ".ai/gates/release-1-task-definitions.yaml",
            "task_id: T-RGOV-001",
            "task_id: {bad: value}",
        )
        with self.assertRaisesRegex(ManifestError, "task_id must be an exact task ID"):
            validate_task_graph(self.repo)


if __name__ == "__main__":
    unittest.main()
