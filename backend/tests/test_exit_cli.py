import json
from pathlib import Path
import subprocess
import sys

from test_exit_package import package


def test_offline_verifier_does_not_claim_complete_or_accept_duplicate_fields(tmp_path):
    # These are generated test artifacts, not source-file rewrites.
    path = tmp_path / "core.json"
    path.write_text(json.dumps(package()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "verify_exit.py"
    run = lambda *flags: subprocess.run([sys.executable, str(script), str(path), *flags], capture_output=True, text=True, timeout=10)
    valid = run()
    assert valid.returncode == 0 and json.loads(valid.stdout)["lifecycle_complete"] is False
    assert run("--require-complete").returncode == 1
    path.write_text('{"workspace_id":"synthetic","workspace_id":"duplicate"}', encoding="utf-8")
    assert run().returncode == 1
