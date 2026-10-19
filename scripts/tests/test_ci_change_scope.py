"""Fail-closed CI scope regression tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase, mock
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "ci_change_scope.py"
spec = importlib.util.spec_from_file_location("ci_change_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class DocsOnlyTests(TestCase):
    def test_readme_and_manifest_are_fast(self):
        self.assertTrue(scope.docs_only(["README.md", "PUBLIC_MANIFEST.json"]))

    def test_bilingual_docs_are_fast(self):
        self.assertTrue(scope.docs_only(["README.md", "README_EN.md", "PUBLIC_MANIFEST.json"]))

    def test_reviewed_presentation_docs_are_fast(self):
        self.assertTrue(scope.docs_only(["docs/README.md", "docs/ENGINEERING_OVERVIEW.md"]))

    def test_manifest_only_forces_full(self):
        self.assertFalse(scope.docs_only(["PUBLIC_MANIFEST.json"]))

    def test_no_changes_force_full(self):
        self.assertFalse(scope.docs_only([]))

    def test_backend_change_forces_full(self):
        self.assertFalse(scope.docs_only(["README.md", "backend/local.py"]))

    def test_ci_or_security_script_change_forces_full(self):
        for path in (".github/workflows/synthetic-ci.yml", "scripts/public_guard.py", "scripts/scan_public.py", "scripts/ci_change_scope.py"):
            with self.subTest(path=path):
                self.assertFalse(scope.docs_only(["README.md", "PUBLIC_MANIFEST.json", path]))

    def test_canonical_specs_and_release_gate_change_force_full(self):
        for path in ("docs/specs/class-os-v1/requirements.md", ".ai/gates/release-1-tasks.yaml"):
            with self.subTest(path=path):
                self.assertFalse(scope.docs_only(["README.md", path]))

    def test_security_document_requires_full(self):
        self.assertFalse(scope.docs_only(["README.md", "SECURITY.md"]))

    def test_uploaded_binary_requires_full(self):
        self.assertFalse(scope.docs_only(["README.md", "assets/private-photo.png"]))

    def test_unrecognized_event_requires_full(self):
        h = "a" * 40
        self.assertIsNone(scope.changed_paths("workflow_dispatch", h, h, h))

    def test_invalid_or_initial_sha_requires_full(self):
        head = "a" * 40
        self.assertIsNone(scope.changed_paths("push", head, "0" * 40, ""))
        self.assertIsNone(scope.changed_paths("push", "malicious", "b" * 40, ""))

    @mock.patch.object(scope.subprocess, "run")
    def test_pull_request_compares_base_to_merge_head(self, runner):
        runner.side_effect = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"README.md\0PUBLIC_MANIFEST.json\0", b""),
        ]
        base, head = "a" * 40, "b" * 40
        self.assertEqual(
            ["README.md", "PUBLIC_MANIFEST.json"],
            scope.changed_paths("pull_request", head, "", base),
        )
        self.assertEqual(runner.call_args_list[1].args[0][-2:], [base, head])

    @mock.patch.object(scope.subprocess, "run")
    def test_missing_merge_ancestor_forces_full(self, runner):
        runner.return_value = subprocess.CompletedProcess([], 1, b"", b"")
        self.assertIsNone(scope.changed_paths("pull_request", "b" * 40, "", "a" * 40))

    @mock.patch.object(scope.subprocess, "run")
    def test_git_diff_failure_forces_full(self, runner):
        runner.side_effect = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 1, b"", b"fatal"),
        ]
        self.assertIsNone(scope.changed_paths("push", "b" * 40, "a" * 40, ""))
