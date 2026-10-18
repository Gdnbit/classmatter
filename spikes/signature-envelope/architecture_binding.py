"""Synthetic E-ARCH-002 current-source binding after DSSE/policy verification.

This is a candidate oracle, not an approval issuer or feature authorization gate.
Production composition must supply a trusted checkout root and ExpectedContext.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from signature_envelope import (
    AdmissionDecision, AdmissionError, ExpectedContext, VerifiedRegistrySnapshot,
    verify_admission,
)


ARCHITECTURE = "docs/specs/class-os-v1/architecture.md"
ADR = "docs/specs/class-os-v1/architecture-decision.md"
CONSTRAINTS = "docs/00-项目总览/项目宪章与开发约束.md"
SPIKES = {
    "language_runtime": "spikes/language/evidence/language-spike.latest.json",
    "agent_runtime": "spikes/agent-read-draft/evidence/routing-eval.latest.json",
    "self_host_resources": "spikes/self-host/evidence/self-host-spike.latest.json",
    "signature_envelope": "spikes/signature-envelope/evidence/signature-envelope.latest.json",
}
ADR_IDS = tuple(f"ADR-{i:03d}" for i in range(1, 8))
HEADING = re.compile(r"^## (ADR-[0-9]{3})[：:]", re.MULTILINE)
MAX_SOURCE_BYTES = 2_000_000
SOURCES = (ARCHITECTURE, ADR, CONSTRAINTS, *SPIKES.values())


def _source(root: Path, relative: str) -> bytes:
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise AdmissionError(f"architecture source is a link: {relative}")
    try:
        data = current.read_bytes()
    except OSError as exc:
        raise AdmissionError(f"architecture source unavailable: {relative}") from exc
    if not data or len(data) > MAX_SOURCE_BYTES or data.startswith(b"\xef\xbb\xbf"):
        raise AdmissionError(f"architecture source byte contract invalid: {relative}")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _adr_hashes(raw: bytes) -> dict[str, str]:
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdmissionError("ADR source must be UTF-8") from exc
    if "\r" in content.replace("\r\n", ""):
        raise AdmissionError("ADR source has unsupported line endings")
    content = content.replace("\r\n", "\n")
    matches = list(HEADING.finditer(content))
    ids = [match.group(1) for match in matches]
    if ids[:7] != list(ADR_IDS) or len(ids) != len(set(ids)):
        raise AdmissionError("ADR-001—007 sections are absent, reordered or repeated")
    sections = {
        match.group(1): content[match.start():matches[index + 1].start() if index + 1 < len(matches) else len(content)]
        for index, match in enumerate(matches)
    }
    adr006 = sections["ADR-006"]
    part = re.search(r"^### ADR-006B[：:][^\n]*\n(?P<body>.*?)(?=^### |\Z)", adr006,
                     flags=re.MULTILINE | re.DOTALL)
    if part is None or re.findall(r"^状态：(.+)$", part.group("body"), re.MULTILINE) != ["accepted"]:
        raise AdmissionError("ADR-006B is not finally accepted")
    return {identifier: _sha(sections[identifier].encode("utf-8")) for identifier in ADR_IDS}


def binding_hashes(root: Path) -> dict[str, Any]:
    """Compute an exact, repository-owned R1 binding map; no payload paths."""
    if not isinstance(root, Path):
        raise AdmissionError("trusted checkout root is missing")
    return {
        "approved_architecture_sha256": _sha(_source(root, ARCHITECTURE)),
        "approved_adr_sha256": _adr_hashes(_source(root, ADR)),
        "approved_spike_evidence": {
            name: _sha(_source(root, relative)) for name, relative in SPIKES.items()
        },
        "constraints_sha256": _sha(_source(root, CONSTRAINTS)),
    }


def _checkout_matches_target(root: Path, target_commit: str) -> None:
    """Require a clean tracked source set at the exact commit, not a live overlay."""
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=5,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=5,
        ).stdout.strip()
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", *SOURCES],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        clean = subprocess.run(
            ["git", "-C", str(root), "diff", "HEAD", "--quiet"],
            check=False, capture_output=True, timeout=5,
        )
        untracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdmissionError("trusted checkout cannot be verified") from exc
    if (Path(top).resolve() != root.resolve() or head != target_commit
            or len(tracked.stdout.splitlines()) != len(SOURCES)
            or clean.returncode != 0 or untracked):
        raise AdmissionError("architecture sources do not match the trusted target commit")


def verify_architecture_binding(
    envelope: dict[str, Any], registry_snapshot: VerifiedRegistrySnapshot,
    now: datetime, expected: ExpectedContext, trusted_checkout_root: Path,
) -> AdmissionDecision:
    """Verify DSSE and current files; never turn eligibility into release authority."""
    if expected.artifact_type != "architecture-approval":
        raise AdmissionError("architecture binding requires architecture-approval context")
    decision = verify_admission(envelope, registry_snapshot, now, expected)
    if decision.payload["referenced_artifact_ids"]:
        raise AdmissionError("architecture approval may not introduce generic references")
    _checkout_matches_target(trusted_checkout_root, expected.target_commit)
    current = binding_hashes(trusted_checkout_root)
    for field, digest in current.items():
        if decision.payload[field] != digest:
            raise AdmissionError(f"architecture current-source binding mismatch: {field}")
    if decision.release_authorized:
        raise AdmissionError("architecture approval is not release authorization")
    return decision
