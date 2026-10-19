"""Classify safe documentation-only changes for CI; uncertain cases run full checks.

The SHA-locked public guard and full-history secret scan always run independently
of this classification. A docs-only decision never authorizes publication.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "PUBLIC_MANIFEST.json"

# An explicit, narrow allowlist: canonical specs, CI, scripts, security
# policies and release gates are never classified as lightweight docs.
PRESENTATION_DOCS = frozenset({
    "README.md",
    "README_EN.md",
    "BRAND_MIGRATION_MATRIX.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/ENGINEERING_OVERVIEW.md",
    "docs/OPEN_SOURCE_READINESS.md",
    "docs/PUBLIC_AUDIT.md",
})
HEX_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def docs_only(paths: list[str]) -> bool:
    changed = set(paths)
    # A manifest-only edit must never classify as documentation-only.
    return bool(changed & PRESENTATION_DOCS) and changed <= (PRESENTATION_DOCS | {MANIFEST})


def changed_paths(event: str, head: str, before: str, pr_base: str, cwd: Path = ROOT) -> list[str] | None:
    if not HEX_SHA.fullmatch(head):
        return None
    if event == "pull_request":
        start = pr_base
    elif event == "push":
        start = before
    else:
        # Manual dispatch or unrecognized events must run full engineering.
        return None
    if not HEX_SHA.fullmatch(start) or start == "0" * 40:
        return None
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", start, head],
        cwd=cwd, capture_output=True, check=False,
    )
    if ancestor.returncode != 0:
        return None
    change = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", "-z", start, head],
        cwd=cwd, capture_output=True, check=False,
    )
    if change.returncode != 0:
        return None
    try:
        return [p.decode("utf-8") for p in change.stdout.split(b"\0") if p]
    except UnicodeDecodeError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--before", default="")
    parser.add_argument("--pr-base", default="")
    parser.add_argument("--github-output", required=True)
    options = parser.parse_args()

    # Fail closed: missing commits, shallow/invalid history, encoding errors,
    # force pushes, unknown events, and any script error all require full CI.
    try:
        paths = changed_paths(options.event, options.head, options.before, options.pr_base)
        lightweight = paths is not None and docs_only(paths)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Change classification inconclusive: {type(exc).__name__}", file=sys.stderr)
        paths = None
        lightweight = False

    label = "DOCS_ONLY" if lightweight else "FULL_ENGINEERING"
    print(f"CI scope: {label}; changed paths: {len(paths) if paths is not None else 'unknown'}")
    with Path(options.github_output).open("a", encoding="utf-8") as output:
        output.write(f"docs_only={'true' if lightweight else 'false'}\n")


if __name__ == "__main__":
    main()
