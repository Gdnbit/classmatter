"""Exact public bytes must survive Windows-style checkout conversion settings."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PublicCheckoutTests(unittest.TestCase):
    def test_reviewed_tree_survives_autocrlf_true_without_private_history(self):
        manifest = json.loads((ROOT / "PUBLIC_MANIFEST.json").read_text(encoding="utf-8"))
        # Only indexed public files, no ignored artifacts, refs, authors or .git.
        with tempfile.TemporaryDirectory(prefix="classmatter-checkout-") as directory:
            target = Path(directory).resolve()
            prefix = target.as_posix() + "/"
            subprocess.run(["git", "-C", str(ROOT), "-c", "core.autocrlf=true", "checkout-index", "--all", "--prefix=" + prefix],
                           check=True, capture_output=True)
            self.assertFalse((target / ".git").exists())
            for relative, entry in manifest["files"].items():
                with self.subTest(path=relative):
                    self.assertEqual(entry["sha256"], hashlib.sha256((target / relative).read_bytes()).hexdigest())
            self.assertEqual((ROOT / "PUBLIC_MANIFEST.json").read_bytes(), (target / "PUBLIC_MANIFEST.json").read_bytes())
