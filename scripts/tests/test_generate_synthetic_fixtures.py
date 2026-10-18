from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_synthetic_fixtures import (
    DEFAULT_SEED,
    FixtureError,
    build_fixture_bundle,
    check_fixture_directory,
    render_fixture_files,
    scan_for_sensitive_patterns,
    write_fixture_directory,
)


class SyntheticFixtureFactoryTests(unittest.TestCase):
    def test_same_seed_is_byte_for_byte_deterministic(self) -> None:
        first = render_fixture_files(DEFAULT_SEED)
        second = render_fixture_files(DEFAULT_SEED)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "audit-failure.synthetic.json",
                "canonical-r1.synthetic.json",
                "fact-events.synthetic.json",
                "proposal-approval.synthetic.json",
                "student-identifier.synthetic.json",
                "workspace-isolation.synthetic.json",
            },
        )

    def test_different_seed_changes_identifiers_not_shape(self) -> None:
        first = build_fixture_bundle(DEFAULT_SEED)
        second = build_fixture_bundle(DEFAULT_SEED + 1)
        self.assertEqual(set(first), set(second))
        self.assertNotEqual(first["workspace_a"]["workspace_id"], second["workspace_a"]["workspace_id"])
        self.assertEqual(set(first["workspace_a"]), set(second["workspace_a"]))

    def test_bundle_contains_required_synthetic_entity_families(self) -> None:
        bundle = build_fixture_bundle(DEFAULT_SEED)
        self.assertTrue(bundle["meta"]["synthetic"])
        self.assertEqual(bundle["meta"]["seed"], DEFAULT_SEED)
        self.assertEqual(bundle["meta"]["clock"], "2026-09-01T08:00:00+08:00")
        for key in (
            "workspace_a",
            "workspace_b",
            "classes",
            "terms",
            "students",
            "student_identifiers",
            "records",
            "tasks",
            "proposals",
            "approval_requests",
            "audit_events",
        ):
            self.assertIn(key, bundle)
            self.assertTrue(bundle[key])

    def test_generated_files_have_no_sensitive_pattern_findings(self) -> None:
        findings = scan_for_sensitive_patterns(render_fixture_files(DEFAULT_SEED))
        self.assertEqual(findings, [])

    def test_scanner_rejects_phone_email_identity_and_secret_shapes(self) -> None:
        bad = {
            "bad.json": (
                b'{"phone":"13812345678","email":"student@example.com",'
                b'"identity":"11010519491231002X","secret":"sk-live-abcdefghijklmnop"}\n'
            )
        }
        findings = scan_for_sensitive_patterns(bad)
        self.assertEqual({finding.pattern for finding in findings}, {"cn_mobile", "email", "cn_identity", "secret_token"})

    def test_tracked_directory_check_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_fixture_directory(output_dir, DEFAULT_SEED)
            summary = check_fixture_directory(output_dir, DEFAULT_SEED)
            self.assertEqual(summary["file_count"], 6)
            path = output_dir / "canonical-r1.synthetic.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(FixtureError, "drift"):
                check_fixture_directory(output_dir, DEFAULT_SEED)


if __name__ == "__main__":
    unittest.main()
