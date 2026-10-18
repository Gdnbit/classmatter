"""Default-deny public tree guard. No implicit manifest approval or private mappings."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "PUBLIC_MANIFEST.json"
FORBIDDEN_PARTS = {".git", ".hg", ".svn", "release-audit", "handoff", ".local-runtime", "uploads", "raw", "node_modules", ".venv", "test-results", "playwright-report", "dist", "coverage", ".pytest_cache", "__pycache__", ".vite"}
BINARY_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp", ".ico", ".pdf", ".doc", ".xls", ".ppt", ".docx", ".xlsx", ".pptx", ".exe", ".dll", ".db", ".sqlite", ".map", ".wav", ".mp3", ".mp4", ".ogg", ".mov"}
PATTERNS = {
    "user-machine-path": re.compile(r"[A-Z]:[/\\](?:Users|Works|PythonData)[/\\]", re.I),
    "phone-shape": re.compile(r"(?<![A-Za-z0-9])1[3-9][0-9]{9}(?![A-Za-z0-9])"),
    "national-id-shape": re.compile(r"(?<![A-Za-z0-9])[1-9][0-9]{5}(?:19|20)[0-9]{2}[01][0-9][0-3][0-9][0-9]{3}[0-9Xx](?![A-Za-z0-9])"),
    "conversation-link": re.compile(r"chatgpt-conversation:|chatgpt\.com/c/"),
    "email-shape": re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
}


def validate(root: Path, manifest: dict, paths: list[str], require_license=False):
    errors = []
    entries = manifest.get("files", {})
    if manifest.get("schema_version") != 1 or not isinstance(entries, dict):
        return ["invalid manifest"]
    actual = set(paths) - {MANIFEST}
    if actual != set(entries):
        errors += ["unreviewed or missing file: " + p for p in sorted(actual ^ set(entries))]
    for path in sorted(actual & set(entries)):
        candidate = root / path
        if (Path(path).is_absolute() or ".." in Path(path).parts or "\\" in path or ":" in path
                or candidate.is_symlink() or candidate.is_junction()
                or any(parent.is_symlink() or parent.is_junction() for parent in candidate.parents if parent != root.parent)
                or not candidate.resolve().is_relative_to(root.resolve())):
            errors.append("unsafe path: " + path); continue
        if set(Path(path).parts) & FORBIDDEN_PARTS or candidate.suffix.lower() in BINARY_SUFFIXES:
            errors.append("forbidden publication material: " + path); continue
        if candidate.name.startswith(".env") and candidate.name != ".env.example":
            errors.append("private environment file: " + path); continue
        payload = candidate.read_bytes()
        if b"\x00" in payload or payload.startswith((b"PK\x03\x04", b"PK\x05\x06", b"7z\xbc\xaf\x27\x1c", b"\x89PNG", b"\xff\xd8\xff", b"%PDF", b"\xd0\xcf\x11\xe0")):
            errors.append("disguised binary/archive: " + path); continue
        if hashlib.sha256(payload).hexdigest() != entries[path].get("sha256"):
            errors.append("unreviewed content change: " + path)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("unreviewed binary: " + path); continue
        for number, line in enumerate(text.splitlines(), 1):
            for rule, pattern in PATTERNS.items():
                if pattern.search(line):
                    fingerprint = hashlib.sha256(line.encode()).hexdigest()
                    exceptions = entries[path].get("reviewed_pattern_exceptions", [])
                    if {"rule": rule, "line_sha256": fingerprint} not in exceptions:
                        errors.append(f"{rule}: {path}:{number}")
    if require_license and not (root / "LICENSE").is_file():
        errors.append("BLOCKED: owner-approved root LICENSE missing")
    return errors


def paths(root=ROOT):
    output = subprocess.check_output(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    return sorted(set(x.decode() for x in output.split(b"\0") if x))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--require-license", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
        errors = validate(ROOT, manifest, paths(), args.require_license)
    except (OSError, ValueError, KeyError):
        raise SystemExit("BLOCKED: reviewed public manifest unavailable or invalid") from None
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)
    print("Reviewed public paths/content and privacy patterns verified; not publication authorization")


if __name__ == "__main__":
    main()
