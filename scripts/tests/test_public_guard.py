"""Release guard failures must remain visible; never auto-approve new content."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("public_guard", Path(__file__).resolve().parents[1] / "public_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class PublicGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "safe.txt").write_text("synthetic", encoding="utf-8")
        self.manifest = {"schema_version": 1, "files": {"safe.txt": {"sha256": hashlib.sha256(b"synthetic").hexdigest()}}}

    def test_reviewed_content_passes(self):
        self.assertEqual([], guard.validate(self.root, self.manifest, ["safe.txt"]))

    def test_added_file_rejected(self):
        self.assertTrue(guard.validate(self.root, self.manifest, ["safe.txt", "new.txt"]))

    def test_mutation_rejected(self):
        (self.root / "safe.txt").write_text("changed", encoding="utf-8")
        self.assertTrue(guard.validate(self.root, self.manifest, ["safe.txt"]))

    def test_license_is_separate_blocker(self):
        self.assertTrue(guard.validate(self.root, self.manifest, ["safe.txt"], require_license=True))

    def test_reapproved_archive_still_rejected(self):
        (self.root / "unsafe.zip").write_bytes(b"synthetic")
        self.manifest["files"]["unsafe.zip"] = self.manifest["files"].pop("safe.txt")
        self.assertTrue(guard.validate(self.root, self.manifest, ["unsafe.zip"]))

    def test_symlink_rejected(self):
        # Use a path traversal without requiring elevated symlink privileges.
        self.manifest["files"]["../outside.txt"] = {"sha256": "0" * 64}
        self.assertTrue(guard.validate(self.root, self.manifest, ["../outside.txt"]))

    def test_force_tracked_runtime_json_rejected_even_if_hash_reviewed(self):
        path = "test-results/unsafe.json"
        (self.root / "test-results").mkdir()
        (self.root / path).write_bytes(b"{}")
        manifest = {"schema_version": 1, "files": {path: {"sha256": hashlib.sha256(b"{}").hexdigest()}}}
        self.assertTrue(guard.validate(self.root, manifest, [path]))

    def test_disguised_archive_and_private_environment_are_rejected(self):
        for path, payload in (("safe.txt", b"PK\x05\x06"), (".env.backup", b"synthetic")):
            with self.subTest(path=path):
                (self.root / path).write_bytes(payload)
                manifest = {"schema_version": 1, "files": {path: {"sha256": hashlib.sha256(payload).hexdigest()}}}
                self.assertTrue(guard.validate(self.root, manifest, [path]))
