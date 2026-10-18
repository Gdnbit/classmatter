"""Synthetic E-ARCH-002 candidate; never grants feature or real-data authority."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from architecture_binding import binding_hashes, verify_architecture_binding
from signature_envelope import (
    ARTIFACT_POLICIES, REGISTRY_PAYLOAD_TYPE, AdmissionError, ExpectedContext,
    canonicalize_payload, sha256_hex, sign_envelope, verify_registry_envelope,
)


NOW = datetime(2029, 6, 1, tzinfo=UTC)
DEFINITION = "d" * 64
EVIDENCE = {
    "language_runtime": "spikes/language/evidence/language-spike.latest.json",
    "agent_runtime": "spikes/agent-read-draft/evidence/routing-eval.latest.json",
    "self_host_resources": "spikes/self-host/evidence/self-host-spike.latest.json",
    "signature_envelope": "spikes/signature-envelope/evidence/signature-envelope.latest.json",
}


def _key(seed: int, role: str, usage: str):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return {
        "key_id": f"synthetic-{usage}-{role}", "signer_id": f"synthetic-{role}-{seed}",
        "algorithm": "Ed25519", "public_key": private.public_key().public_bytes_raw().hex(),
        "role": role, "key_usage": usage, "not_before": "2029-01-01T00:00:00Z",
        "not_after": "2030-01-01T00:00:00Z", "status": "active", "revoked_at": None,
    }, private


def _root(tmp_path: Path) -> Path:
    files = {
        "docs/specs/class-os-v1/architecture.md": "# Synthetic architecture\n",
        "docs/specs/class-os-v1/architecture-decision.md": (
            "# Synthetic ADR\n\n" + "".join(
                f"## ADR-{i:03d}：synthetic\n\n"
                + ("### ADR-006B：synthetic\n\n状态：accepted\n\n" if i == 6 else "")
                + "Decision synthetic.\n\n" for i in range(1, 9)
            )
        ),
        "docs/00-项目总览/项目宪章与开发约束.md": "# Synthetic constraints\n",
        **{path: '{"synthetic":true}\n' for path in EVIDENCE.values()},
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", "."], check=True)
    subprocess.run([
        "git", "-C", str(tmp_path), "-c", "user.name=Synthetic Test",
        "-c", "user.email=synthetic@example.invalid", "commit", "-qm", "synthetic baseline",
    ], check=True)
    return tmp_path


def _head(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def _signed(root: Path, *, payload_change=None):
    policy = ARTIFACT_POLICIES["architecture-approval"]
    root_keys, root_signers = [], []
    for seed, role in zip((31, 32, 33), ("offline-root", "security", "operations"), strict=True):
        record, private = _key(seed, role, "registry-approval")
        root_keys.append(record)
        root_signers.append((record["key_id"], private))
    keys, signers = [], []
    for seed, role in enumerate(sorted(policy.roles), start=40):
        record, private = _key(seed, role, policy.key_usage)
        keys.append(record)
        signers.append((record["key_id"], private))
    registry = {
        "schema_version": 1, "generation": 1, "previous_registry_sha256": "a" * 64,
        "issued_at": "2029-01-01T00:00:00Z", "expires_at": "2030-01-01T00:00:00Z",
        "issued_artifacts": ["architecture-synthetic-001"], "revoked_artifacts": [],
        "keys": keys,
    }
    digest = sha256_hex(canonicalize_payload(registry))
    snapshot = verify_registry_envelope(
        sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, root_signers),
        {"schema_version": 1, "keys": root_keys},
        {"minimum_generation": 1, "registry_sha256": digest}, NOW,
    )
    payload = {
        "schema_version": 1, "artifact_type": "architecture-approval",
        "artifact_id": "architecture-synthetic-001", "lifecycle": "reusable-attestation",
        "issued_at": "2029-05-31T00:00:00Z", "not_before": "2029-05-31T00:00:00Z",
        "expires_at": "2029-06-30T00:00:00Z", "nonce": "00000000000000000000000000000001",
        "target_release_digest": "sha256:" + "b" * 64, "target_commit": _head(root),
        "definition_bundle_sha256": DEFINITION,
        "registry": {"generation": 1, "sha256": digest},
        "required_roles": sorted(policy.roles), "required_key_usage": policy.key_usage,
        "referenced_artifact_ids": [],
        **binding_hashes(root),
    }
    if payload_change:
        payload_change(payload)
    envelope = sign_envelope(payload, policy.payload_type, signers)
    expected = ExpectedContext(
        artifact_type="architecture-approval",
        target_release_digest=payload["target_release_digest"],
        target_commit=_head(root), definition_bundle_sha256=DEFINITION,
    )
    return envelope, snapshot, expected


def test_current_sources_match_but_never_authorize_feature(tmp_path):
    root = _root(tmp_path)
    envelope, snapshot, expected = _signed(root)
    decision = verify_architecture_binding(envelope, snapshot, NOW, expected, root)
    assert decision.eligible is True
    assert decision.release_authorized is False


@pytest.mark.parametrize("field", [
    "approved_architecture_sha256", "constraints_sha256",
    "approved_adr_sha256", "approved_spike_evidence",
])
def test_validly_resigned_source_drift_is_rejected(tmp_path, field):
    root = _root(tmp_path)
    envelope, snapshot, expected = _signed(root, payload_change=lambda payload: (
        payload[field].update({next(iter(payload[field])): "0" * 64})
        if isinstance(payload[field], dict) else payload.update({field: "0" * 64})
    ))
    with pytest.raises(AdmissionError):
        verify_architecture_binding(envelope, snapshot, NOW, expected, root)


def test_current_file_changes_after_signing_are_rejected(tmp_path):
    root = _root(tmp_path)
    envelope, snapshot, expected = _signed(root)
    path = root / "docs/specs/class-os-v1/architecture-decision.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Decision synthetic.",
                    "Decision changed.", 1), encoding="utf-8", newline="\n")
    with pytest.raises(AdmissionError):
        verify_architecture_binding(envelope, snapshot, NOW, expected, root)


def test_unfinalized_adr_006b_is_rejected_even_with_matching_digest(tmp_path):
    root = _root(tmp_path)
    path = root / "docs/specs/class-os-v1/architecture-decision.md"
    path.write_text(path.read_text(encoding="utf-8").replace("状态：accepted", "状态：pending"),
                    encoding="utf-8", newline="\n")
    with pytest.raises(AdmissionError):
        _signed(root)


def test_a_valid_signature_for_an_old_commit_cannot_bind_new_checkout(tmp_path):
    root = _root(tmp_path)
    envelope, snapshot, expected = _signed(root)
    path = root / "docs/specs/class-os-v1/architecture.md"
    path.write_text("# New synthetic architecture\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(root), "add", "--", "."], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Synthetic Test",
        "-c", "user.email=synthetic@example.invalid", "commit", "-qm", "new target",
    ], check=True)
    with pytest.raises(AdmissionError):
        verify_architecture_binding(envelope, snapshot, NOW, expected, root)


def test_resigned_uncommitted_overlay_cannot_claim_old_commit(tmp_path):
    root = _root(tmp_path)
    path = root / "docs/specs/class-os-v1/architecture.md"
    path.write_text("# Uncommitted synthetic architecture\n", encoding="utf-8", newline="\n")
    envelope, snapshot, expected = _signed(root)
    with pytest.raises(AdmissionError):
        verify_architecture_binding(envelope, snapshot, NOW, expected, root)


def test_untracked_runtime_code_cannot_claim_clean_target(tmp_path):
    root = _root(tmp_path)
    envelope, snapshot, expected = _signed(root)
    (root / "new-adapter.py").write_text("# synthetic untracked code\n", encoding="utf-8")
    with pytest.raises(AdmissionError):
        verify_architecture_binding(envelope, snapshot, NOW, expected, root)


@pytest.mark.parametrize("field", ["approved_adr_sha256", "approved_spike_evidence"])
def test_extra_or_missing_digest_keys_are_rejected(tmp_path, field):
    root = _root(tmp_path)
    for change in (lambda mapping: mapping.pop(next(iter(mapping))),
                   lambda mapping: mapping.update({"EXTRA": "0" * 64})):
        def alter(payload):
            change(payload[field])
        envelope, snapshot, expected = _signed(root, payload_change=alter)
        with pytest.raises(AdmissionError):
            verify_architecture_binding(envelope, snapshot, NOW, expected, root)
