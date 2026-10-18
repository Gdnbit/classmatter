"""Regression guard: local-only frontend source must not make the build look green."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_SOURCE = ROOT / "apps/web/src"


class RepositoryPortabilityTests(unittest.TestCase):
    def test_runtime_data_paths_remain_ignored(self):
        for relative in (
            "data/runtime.json", "apps/web/data/runtime.json",
            "uploads/attachment.bin", ".local-runtime/postgresql/archive.zip",
        ):
            with self.subTest(path=relative):
                check = subprocess.run(
                    ["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", "--", relative],
                    check=False, capture_output=True,
                )
                self.assertEqual(0, check.returncode, f"runtime path is no longer ignored: {relative}")

    def test_all_frontend_source_files_are_tracked_and_not_ignored(self):
        tracked_result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "apps/web/src"],
            check=True, capture_output=True,
        )
        tracked = {
            item.decode("utf-8") for item in tracked_result.stdout.split(b"\0") if item
        }
        source_files = sorted(path for path in WEB_SOURCE.rglob("*") if path.is_file())
        self.assertTrue(source_files, "apps/web/src unexpectedly has no source files")
        missing = []
        ignored = []
        for path in source_files:
            relative = path.relative_to(ROOT).as_posix()
            if relative not in tracked:
                missing.append(relative)
            check = subprocess.run(
                ["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", "--", relative],
                check=False, capture_output=True,
            )
            if check.returncode == 0:
                ignored.append(relative)
            elif check.returncode != 1:
                self.fail(f"git check-ignore failed for {relative}: {check.returncode}")
        self.assertEqual([], missing, f"frontend source missing from Git index: {missing}")
        self.assertEqual([], ignored, f"frontend source hidden by ignore rules: {ignored}")


if __name__ == "__main__":
    unittest.main()
