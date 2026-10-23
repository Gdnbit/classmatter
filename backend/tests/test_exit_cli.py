import json
from pathlib import Path
import subprocess
import sys
import hashlib
import importlib.util
import os

import pytest

from test_exit_package import package, rich_package, rehash


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


@pytest.mark.parametrize("change", ["copy", "format", "metadata", "core", "corrupt", "duplicate", "oversize", "missing", "complete"])
def test_offline_transfer_comparison_has_no_implicit_import_or_complete_claim(tmp_path, change):
    source, destination = tmp_path / "source.json", tmp_path / "copy.json"
    bundle = rich_package()
    raw = json.dumps(bundle, ensure_ascii=False).encode()
    source.write_bytes(raw)
    destination.write_bytes(raw)
    if change == "format":
        destination.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    elif change == "metadata":
        bundle["created_at"] = "2026-10-23T00:00:00+00:00"
        destination.write_text(json.dumps(rehash(bundle)), encoding="utf-8")
    elif change == "core":
        bundle["core"]["manual_task"][0]["title"] = "合成变更标题"
        destination.write_text(json.dumps(rehash(bundle)), encoding="utf-8")
    elif change == "corrupt":
        destination.write_bytes(b"synthetic-private-error-canary")
    elif change == "duplicate":
        destination.write_bytes(b'{"secret-canary":0,"secret-canary":1}')
    elif change == "oversize":
        destination.write_bytes(b" " * 2097153)
    elif change == "missing":
        destination.unlink()
    before = {path: path.read_bytes() for path in (source, destination) if path.exists()}
    script = Path(__file__).resolve().parents[1] / "verify_exit.py"
    flags = ["--require-complete"] if change == "complete" else []
    result = subprocess.run([sys.executable, str(script), str(source), "--compare-with", str(destination), *flags],
                            capture_output=True, text=True, timeout=10)
    assert {path: path.read_bytes() for path in before} == before
    assert "secret-canary" not in result.stdout + result.stderr
    assert "synthetic-private-error-canary" not in result.stdout + result.stderr
    if change in ("corrupt", "duplicate", "oversize", "missing", "complete"):
        assert result.returncode == 1 and not result.stdout
        assert result.stderr == "Package rejected: invalid/incomplete synthetic exit. No database was changed.\n"
        return
    report = json.loads(result.stdout)
    assert report["lifecycle_complete"] is False
    assert report["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert "合成学生" not in result.stdout and str(source) not in result.stdout
    assert report["comparison"] == {"same_file_bytes": change == "copy", "same_package": change in ("copy", "format"), "same_core": change != "core"}
    assert result.returncode == (0 if change == "copy" else 2)


def test_verifier_rejects_non_regular_input_without_database_or_sdk_imports(tmp_path):
    script = Path(__file__).resolve().parents[1] / "verify_exit.py"
    spec = importlib.util.spec_from_file_location("exit_verifier_test", script)
    module = importlib.util.module_from_spec(spec)
    before = set(sys.modules)
    spec.loader.exec_module(module)
    assert not any(name.startswith(("class_os.infrastructure", "pydantic_ai", "sqlalchemy")) for name in set(sys.modules) - before)
    with pytest.raises((ValueError, OSError)):
        module.load_package(tmp_path)
    if os.name != "nt":
        fifo = tmp_path / "package.fifo"
        os.mkfifo(fifo)
        result = subprocess.run([sys.executable, str(script), str(fifo)], capture_output=True, text=True, timeout=5)
        assert result.returncode == 1 and not result.stdout


def test_verifier_rejects_leaf_link_without_reading_target(tmp_path):
    target, linked = tmp_path / "original.json", tmp_path / "linked.json"
    raw = json.dumps(package()).encode()
    target.write_bytes(raw)
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("Host policy does not permit symbolic-link creation")
    script = Path(__file__).resolve().parents[1] / "verify_exit.py"
    result = subprocess.run([sys.executable, str(script), str(linked)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 1 and not result.stdout and target.read_bytes() == raw


@pytest.mark.parametrize("raw", [b'{"private-error-canary":NaN}', b'{"x":Infinity}', b'\xff\xfe\x00', b'[' * 1200])
def test_verifier_invalid_json_and_encoding_never_dump_input(tmp_path, raw):
    path = tmp_path / "untrusted.json"
    path.write_bytes(raw)
    script = Path(__file__).resolve().parents[1] / "verify_exit.py"
    result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 1 and not result.stdout
    assert "private-error-canary" not in result.stderr and str(path) not in result.stderr
