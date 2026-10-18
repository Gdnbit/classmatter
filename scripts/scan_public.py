"""Pinned Gitleaks scan of reviewed public files and optional full local history.

Only redacted local reports are written. No upload, token, action or remote needed.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from public_guard import ROOT, MANIFEST, paths, validate

VERSION = "8.30.1"
ASSETS = {
    "Windows": ("windows_x64.zip", "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"),
    "Linux": ("linux_x64.tar.gz", "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"),
}


def scanner(directory):
    system = platform.system()
    if platform.machine().lower() not in ("amd64", "x86_64") or system not in ASSETS:
        raise SystemExit("Reviewed x64 Windows/Linux scanner required")
    asset, expected = ASSETS[system]
    filename = f"gitleaks_{VERSION}_{asset}"
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/{filename}"
    payload = urllib.request.urlopen(url, timeout=60).read()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise SystemExit("Scanner checksum mismatch")
    binary = "gitleaks.exe" if system == "Windows" else "gitleaks"
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            content = archive.read(binary)
    else:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            content = archive.extractfile(binary).read()
    target = directory / binary
    target.write_bytes(content)
    target.chmod(0o700)
    return target


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    errors = validate(ROOT, manifest, paths())
    if errors:
        raise SystemExit("Public guard failed; inspect with public_guard.py")
    reviewed = json.loads((ROOT / "SECRET_SCAN_REVIEW.json").read_text(encoding="utf-8"))["findings"]
    reports = ROOT / "test-results/public-secret-scan"
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="classmatter-scan-") as temp:
        scratch = Path(temp)
        binary = scanner(scratch)
        snapshot = scratch / "snapshot"
        snapshot.mkdir()
        for path in [*manifest["files"], MANIFEST]:
            destination = snapshot / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, destination)
        modes = [("files", ["dir", str(snapshot)], snapshot)]
        has_history = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD"], capture_output=True).returncode == 0
        if args.history and has_history:
            modes.append(("history", ["git", str(ROOT), "--log-opts=--all --full-history"], ROOT))
        elif args.history:
            print("history: NONE (unborn local repository; no inherited commits)")
        unresolved = 0
        for label, command, scan_root in modes:
            report = reports / (label + ".redacted.json")
            result = subprocess.run([str(binary), *command, "--redact=100", "--no-banner", "--no-color",
                "--log-level=error", "--ignore-gitleaks-allow", "--max-archive-depth=3", "--report-format=json", "--report-path", str(report)],
                capture_output=True)
            if result.returncode not in (0, 1):
                raise SystemExit("Secret scanner failed; inspect local diagnostics, no clean result")
            findings = json.loads(report.read_text(encoding="utf-8")) if report.exists() else []
            for finding in findings:
                raw_path = Path(finding["File"])
                path = raw_path.relative_to(scan_root).as_posix() if raw_path.is_absolute() else raw_path.as_posix()
                if label == "history":
                    payload = subprocess.check_output(["git", "-C", str(ROOT), "show", finding["Commit"] + ":" + path])
                else:
                    payload = (ROOT / path).read_bytes()
                record = {"path": path, "rule": finding["RuleID"], "line": finding["StartLine"], "file_sha256": hashlib.sha256(payload).hexdigest()}
                if not any(all(entry.get(key) == value for key, value in record.items()) and entry.get("reason") for entry in reviewed):
                    unresolved += 1
                    print(f"UNREVIEWED secret pattern: {path}:{record['line']} ({record['rule']})")
            print(f"{label}: findings={len(findings)}; unresolved-so-far={unresolved}; scanner={VERSION}")
        if unresolved:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
