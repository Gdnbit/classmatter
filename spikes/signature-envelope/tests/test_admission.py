from __future__ import annotations

import base64
import copy
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signature_envelope import (
    ARTIFACT_POLICIES,
    REGISTRY_PAYLOAD_TYPE,
    AdmissionError,
    ExpectedContext,
    LifecycleConsumptionFake,
    VerifiedArtifactReference,
    canonicalize_payload,
    dsse_pae,
    sha256_hex,
    sign_envelope,
    validate_reference_graph,
    verify_admission,
    verify_mutable_state_binding,
    verify_registry_envelope,
    verify_rfc8032_known_answer,
)


REPO_ROOT = Path(__file__).parents[3]
NOW = datetime(2029, 6, 1, tzinfo=UTC)
RFC8032_SECRET = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
RFC8032_PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
RFC8032_SIGNATURE = (
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)
SYNTHETIC_REFERENCE_PAYLOADS: dict[str, bytes] = {}


def key_material(
    seed_byte: int, key_id: str, role: str, usage: str
) -> tuple[dict, Ed25519PrivateKey]:
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed_byte]) * 32)
    return (
        {
            "key_id": key_id,
            "signer_id": f"synthetic-{role}-{seed_byte}",
            "algorithm": "Ed25519",
            "public_key": private.public_key().public_bytes_raw().hex(),
            "role": role,
            "key_usage": usage,
            "not_before": "2029-01-01T00:00:00Z",
            "not_after": "2030-01-01T00:00:00Z",
            "status": "active",
            "revoked_at": None,
        },
        private,
    )


def root_material():
    keys, signers = [], []
    for seed, role in zip((21, 22, 23), ("offline-root", "security", "operations"), strict=True):
        record, private = key_material(seed, f"root-{role}", role, "registry-approval")
        keys.append(record)
        signers.append((record["key_id"], private))
    return {"schema_version": 1, "keys": keys}, signers


def admission_payload(registry_hash: str) -> dict:
    reference_context = {
        "target_release_digest": "sha256:" + "b" * 64,
        "target_commit": "0123456789abcdef0123456789abcdef01234567",
        "environment_digest": "sha256:" + "d" * 64,
        "deployment_id": "deployment-synthetic-001",
        "workspace_id": "workspace-synthetic-001",
    }
    scope_context = {
        "owner_ids": ["owner-synthetic-001"],
        "reserved_class_ids": ["class-synthetic-001"],
        "reserved_term_ids": ["term-synthetic-001"],
    }
    return {
        "schema_version": 1,
        "artifact_type": "real-data-admission",
        "artifact_id": "admission-r1-test-001",
        "lifecycle": "renewable-authorization",
        "issued_at": "2029-05-31T00:00:00Z",
        "not_before": "2029-05-31T00:00:00Z",
        "expires_at": "2029-06-30T00:00:00Z",
        "nonce": "00000000000000000000000000000001",
        "target_release_digest": "sha256:" + "b" * 64,
        "target_commit": "0123456789abcdef0123456789abcdef01234567",
        "definition_bundle_sha256": "c" * 64,
        "environment_digest": "sha256:" + "d" * 64,
        "deployment_id": "deployment-synthetic-001",
        "owner_ids": ["owner-synthetic-001"],
        "workspace_id": "workspace-synthetic-001",
        "class_ids": ["class-synthetic-001"],
        "term_ids": ["term-synthetic-001"],
        "scope_allocation_receipt": synthetic_reference(
            "receipt-synthetic-001",
            artifact_type="scope-allocation-receipt",
            **reference_context,
            **scope_context,
        ),
        "allowed_modules": ["roster", "tasks", "timeline-today", "exit-export"],
        "evidence_references": {
            "candidate_gate_report": synthetic_reference(
                "gate-synthetic-001",
                artifact_type="gate-report",
                gate_id="before_release_candidate",
                **reference_context,
            ),
            "pilot_readiness_gate_report": synthetic_reference(
                "gate-synthetic-002",
                artifact_type="gate-report",
                gate_id="before_pilot_readiness",
                **reference_context,
            ),
            "shadow_value_decision": synthetic_reference(
                "shadow-synthetic-001",
                artifact_type="shadow-value-decision",
                **reference_context,
                result="go",
            ),
        },
        "revocation_id": "revoke-synthetic-001",
        "registry": {"generation": 7, "sha256": registry_hash},
        "required_roles": ["operations", "privacy", "product", "security"],
        "required_key_usage": "real-data-admission",
        "referenced_artifact_ids": [],
    }


def synthetic_reference(
    artifact_id: str,
    *,
    artifact_type: str,
    target_release_digest: str,
    target_commit: str,
    environment_digest: str,
    workspace_id: str,
    deployment_id: str | None = None,
    gate_id: str | None = None,
    **extra,
) -> dict:
    policy = ARTIFACT_POLICIES[artifact_type]
    verified_payload = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "lifecycle": policy.lifecycle,
        "target_release_digest": target_release_digest,
        "target_commit": target_commit,
        "environment_digest": environment_digest,
    }
    if artifact_type != "gate-report":
        verified_payload["workspace_id"] = workspace_id
    if deployment_id is not None:
        verified_payload["deployment_id"] = deployment_id
    if artifact_type == "gate-report":
        if gate_id not in {"before_release_candidate", "before_pilot_readiness"}:
            raise ValueError("gate_id is required for synthetic gate-report references")
        verified_payload.update(
            gate_id=gate_id,
            gate_definition_sha256=("1" if gate_id == "before_release_candidate" else "2")
            * 64,
            definition_bundle_sha256="c" * 64,
            verifier_digest="sha256:" + "3" * 64,
        )
    verified_payload.update(extra)
    canonical_payload = canonicalize_payload(verified_payload)
    digest = sha256_hex(canonical_payload)
    SYNTHETIC_REFERENCE_PAYLOADS[artifact_id] = canonical_payload
    reference = {
        "artifact_id": artifact_id,
        "artifact_uri": f"synthetic://signed-artifacts/{artifact_id}.dsse.json",
        "sha256": digest,
        "target_release_digest": target_release_digest,
        "target_commit": target_commit,
        "environment_digest": environment_digest,
    }
    if artifact_type != "gate-report":
        reference["workspace_id"] = workspace_id
    else:
        for field in (
            "gate_id",
            "gate_definition_sha256",
            "definition_bundle_sha256",
            "verifier_digest",
            "target_release_digest",
            "target_commit",
            "environment_digest",
        ):
            reference[field] = verified_payload[field]
    return reference


def synthetic_reference_verifier(
    reference: dict, expected: ExpectedContext, expected_type: str
) -> VerifiedArtifactReference:
    """Test double for the T-REVAL-020 fetch/hash/DSSE verifier port."""

    artifact_id = reference.get("artifact_id")
    if (
        not isinstance(artifact_id, str)
        or reference.get("artifact_uri")
        != f"synthetic://signed-artifacts/{artifact_id}.dsse.json"
        or artifact_id not in SYNTHETIC_REFERENCE_PAYLOADS
    ):
        raise AdmissionError("synthetic reference verification failed")
    canonical_payload = SYNTHETIC_REFERENCE_PAYLOADS[artifact_id]
    payload = json.loads(canonical_payload)
    return VerifiedArtifactReference(
        artifact_id=artifact_id,
        artifact_type=payload["artifact_type"],
        lifecycle=payload["lifecycle"],
        digest=sha256_hex(canonical_payload),
        canonical_payload=canonical_payload,
        registry_generation=7,
        registry_sha256="f" * 64,
        verified_roles=ARTIFACT_POLICIES[payload["artifact_type"]].roles,
    )


def expected_for(payload: dict) -> ExpectedContext:
    return ExpectedContext(
        artifact_type=payload["artifact_type"],
        target_release_digest=payload["target_release_digest"],
        target_commit=payload["target_commit"],
        definition_bundle_sha256=payload.get("definition_bundle_sha256"),
        environment_digest=payload.get("environment_digest"),
        deployment_id=payload.get("deployment_id"),
        workspace_id=payload.get("workspace_id"),
    )


@pytest.fixture
def material():
    keys, signers = [], []
    for seed, role in enumerate(("product", "privacy", "security", "operations"), start=1):
        record, private = key_material(seed, f"test-{role}", role, "real-data-admission")
        keys.append(record)
        signers.append((record["key_id"], private))
    registry = {
        "schema_version": 1,
        "generation": 7,
        "previous_registry_sha256": "a" * 64,
        "issued_at": "2029-01-01T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "issued_artifacts": ["admission-r1-test-001"],
        "revoked_artifacts": [],
        "keys": keys,
    }
    registry_hash = sha256_hex(canonicalize_payload(registry))
    trust_root, root_signers = root_material()
    registry_envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, root_signers)
    pin = {"minimum_generation": 7, "registry_sha256": registry_hash}
    snapshot = verify_registry_envelope(registry_envelope, trust_root, pin, NOW)
    payload = admission_payload(registry_hash)
    envelope = sign_envelope(
        payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, signers
    )
    return {
        "payload": payload,
        "envelope": envelope,
        "registry": registry,
        "snapshot": snapshot,
        "pin": pin,
        "trust_root": trust_root,
        "root_signers": root_signers,
        "signers": signers,
        "expected": expected_for(payload),
    }


def reissue_registry(material: dict, registry: dict, *, prior_pin: dict | None = None) -> dict:
    updated = copy.deepcopy(material)
    registry_hash = sha256_hex(canonicalize_payload(registry))
    registry_envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    pin = prior_pin or {"minimum_generation": registry["generation"], "registry_sha256": registry_hash}
    snapshot = verify_registry_envelope(registry_envelope, material["trust_root"], pin, NOW)
    payload = copy.deepcopy(material["payload"])
    payload["registry"] = {"generation": registry["generation"], "sha256": registry_hash}
    envelope = sign_envelope(
        payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"]
    )
    updated.update(payload=payload, envelope=envelope, registry=registry, snapshot=snapshot, pin=pin)
    updated["expected"] = expected_for(payload)
    return updated


def verify(material: dict, **overrides):
    args = {
        "envelope": material["envelope"],
        "registry_snapshot": material["snapshot"],
        "now": NOW,
        "expected": material["expected"],
        "reference_verifier": synthetic_reference_verifier,
    }
    args.update(overrides)
    return verify_admission(**args)


def issue_policy_artifact(material: dict, artifact_type: str, artifact_id: str, specific: dict):
    policy = ARTIFACT_POLICIES[artifact_type]
    keys, signers = [], []
    for seed, role in enumerate(sorted(policy.roles), start=80):
        record, private = key_material(seed, f"{artifact_id}-{role}", role, policy.key_usage)
        keys.append(record)
        signers.append((record["key_id"], private))
    registry = copy.deepcopy(material["registry"])
    registry["keys"] = keys
    registry["issued_artifacts"] = [artifact_id]
    registry["revoked_artifacts"] = []
    registry_hash = sha256_hex(canonicalize_payload(registry))
    registry_envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    snapshot = verify_registry_envelope(
        registry_envelope,
        material["trust_root"],
        {"minimum_generation": registry["generation"], "registry_sha256": registry_hash},
        NOW,
    )
    payload = {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "lifecycle": policy.lifecycle,
        "issued_at": "2029-05-31T00:00:00Z",
        "not_before": "2029-05-31T00:00:00Z",
        "expires_at": "2029-06-30T00:00:00Z",
        "nonce": f"{80:032x}",
        "target_release_digest": material["payload"]["target_release_digest"],
        "target_commit": material["payload"]["target_commit"],
        "registry": {"generation": snapshot.generation, "sha256": snapshot.sha256},
        "required_roles": sorted(policy.roles),
        "required_key_usage": policy.key_usage,
        "referenced_artifact_ids": [],
        **specific,
    }
    envelope = sign_envelope(payload, policy.payload_type, signers)
    expected = expected_for(payload)
    decision = verify_admission(
        envelope, snapshot, NOW, expected, reference_verifier=synthetic_reference_verifier
    )
    return payload, decision, expected


def test_official_vectors_are_driven_from_machine_manifest():
    path = REPO_ROOT / ".ai/gates/signature-canonicalization-test-vectors.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    vectors = {item["vector_id"]: item for item in document["vectors"]}
    ed = vectors["TV-ED25519-RFC8032-001"]
    assert verify_rfc8032_known_answer(
        secret_key_hex=ed["secret_key_hex"],
        public_key_hex=ed["public_key_hex"],
        message=bytes.fromhex(ed["message_hex"]),
        expected_signature_hex=ed["expected_signature_hex"],
    )
    pae = vectors["TV-DSSE-PAE-001"]
    assert dsse_pae(pae["payload_type_utf8"], pae["payload_utf8"].encode()).decode() == pae["expected_pae_utf8"]
    jcs = vectors["TV-JCS-RFC8785-001"]
    assert canonicalize_payload(json.loads(jcs["source_json"])) == jcs["expected_jcs_utf8"].encode()
    assert vectors["TV-JCS-RFC8785-SORT-001"]["expected_property_order"] == [
        "U+000D", "U+0031", "U+0080", "U+00F6", "U+20AC", "U+1F600", "U+FB33"
    ]
    assert set(vectors["TV-ADMISSION-MUTATIONS-001"]["mutations"]) == {
        "payload-byte", "payload-type", "signature-byte",
        "validly-resigned-target-commit", "validly-resigned-release-digest",
        "validly-resigned-definition-bundle", "validly-resigned-environment",
        "validly-resigned-deployment", "validly-resigned-workspace",
        "missing-required-field", "unknown-field", "duplicate-json-key",
        "nfc-key-collision", "self-reference", "reference-cycle", "unresolved-reference",
        "missing-role", "duplicate-principal", "revoked-key", "revoked-artifact",
        "missing-key-status", "inactive-key", "inactive-root-key",
        "wrong-key-usage", "wrong-root", "missing-registry-role", "old-registry",
        "same-generation-different-hash", "broken-previous-hash", "registry-rotation",
        "invalid-scope-setup-operation", "invalid-scope-setup-allocation-count",
        "missing-reference-verifier", "nested-reference-binding-mismatch",
        "referenced-artifact-type-mismatch", "referenced-payload-digest-mismatch",
        "referenced-role-quorum-mismatch",
        "receipt-owner-mismatch", "receipt-class-scope-mismatch",
        "receipt-term-scope-mismatch", "unknown-admission-module",
        "nested-shadow-non-go",
        "invalid-shadow-result", "receipt-forbidden-business-content",
        "mutable-state-hash-mismatch",
        "renewable-artifact-consumed", "one-time-fake-idempotent-retry",
        "one-time-fake-conflicting-retry",
    }


def test_rfc8785_unicode_sort_and_no_normalization():
    ordered = {"€": 1, "\r": 1, "דּ": 1, "1": 1, "😀": 1, "\x80": 1, "ö": 1}
    assert canonicalize_payload(ordered).decode().startswith(
        '{"\\r":1,"1":1,"\x80":1,"ö":1,"€":1,"😀":1,"דּ":1}'
    )


def test_canonical_artifact_policy_table_matches_machine_policy():
    policy = yaml.safe_load((REPO_ROOT / ".ai/gates/signed-artifact-policy.yaml").read_text(encoding="utf-8"))
    assert set(ARTIFACT_POLICIES) == set(policy["artifact_type_registry"]["allowed_issued_types"])
    for artifact_type, profile in policy["artifact_profiles"].items():
        matrix_name = profile["authorization_matrix"]
        expected = policy["authorization_matrix"][matrix_name]
        actual = ARTIFACT_POLICIES[artifact_type]
        assert actual.roles == frozenset(expected["roles"])
        assert actual.key_usage == expected["key_usage"]
        assert actual.payload_type == profile["payload_type"]
        assert actual.lifecycle == profile["lifecycle"]
        assert actual.required_fields == frozenset(profile["required_fields"])
    assert policy["production_authorization"] is False
    assert set(policy["external_role_key_registry"]["key_record_required_fields"]) == {
        "key_id", "signer_id", "role", "algorithm", "public_key", "key_usage",
        "not_before", "not_after", "status", "revoked_at"
    }
    constraints = policy["artifact_additional_constraints"]
    assert constraints["shadow-value-decision"]["allowed_result"] == ["go", "change", "stop"]
    assert constraints["real-data-scope-setup"]["fixed_allowed_operation"] == (
        "allocate-workspace-bound-empty-scope-only"
    )
    assert constraints["real-data-scope-setup"]["maximum_allocations"] == 1
    assert set(constraints["scope-allocation-receipt"]["forbidden_fields"]) == {
        "student", "person_name", "record", "task", "class_business_state", "term_business_state"
    }


def test_valid_envelope_is_eligible_but_never_release_authorized(material):
    decision = verify(material)
    assert decision.cryptographic_valid and decision.policy_valid and decision.eligible
    assert decision.release_authorized is False
    assert decision.roles == frozenset({"product", "privacy", "security", "operations"})


@pytest.mark.parametrize("mutation", ["payload", "payload_type", "signature"])
def test_dsse_mutations_fail(material, mutation):
    changed = copy.deepcopy(material["envelope"])
    if mutation == "payload":
        raw = base64.b64decode(changed["payload"], validate=True)
        changed["payload"] = base64.b64encode(raw.replace(b"real-data-admission", b"real-data-admissioN")).decode()
    elif mutation == "payload_type":
        changed["payloadType"] += ".changed"
    else:
        signature = bytearray(base64.b64decode(changed["signatures"][0]["sig"], validate=True))
        signature[0] ^= 1
        changed["signatures"][0]["sig"] = base64.b64encode(signature).decode()
    with pytest.raises(AdmissionError):
        verify(material, envelope=changed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_commit", "f" * 40),
        ("target_release_digest", "sha256:" + "e" * 64),
        ("definition_bundle_sha256", "e" * 64),
        ("environment_digest", "sha256:" + "e" * 64),
        ("deployment_id", "deployment-other"),
        ("workspace_id", "workspace-other"),
    ],
)
def test_validly_resigned_stale_or_foreign_context_fails(material, field, value):
    payload = copy.deepcopy(material["payload"])
    payload[field] = value
    envelope = sign_envelope(payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
    with pytest.raises(AdmissionError, match="trusted context mismatch"):
        verify(material, envelope=envelope)


def test_strict_per_artifact_schema_rejects_missing_and_unknown(material):
    for mutation in ("missing", "unknown"):
        payload = copy.deepcopy(material["payload"])
        if mutation == "missing":
            del payload["scope_allocation_receipt"]
        else:
            payload["unexpected"] = True
        envelope = sign_envelope(payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
        with pytest.raises(AdmissionError, match="missing required|unknown fields"):
            verify(material, envelope=envelope)


def test_noncanonical_duplicate_and_nfc_collision_fail(material):
    payload = material["payload"]
    pretty = json.dumps(payload, ensure_ascii=False, indent=2).encode()
    envelope = sign_envelope(pretty, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"], payload_is_bytes=True)
    with pytest.raises(AdmissionError, match="canonical"):
        verify(material, envelope=envelope)

    duplicate = b'{"schema_version":1,"schema_version":1}'
    envelope = sign_envelope(duplicate, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"], payload_is_bytes=True)
    with pytest.raises(AdmissionError, match="duplicate"):
        verify(material, envelope=envelope)

    collision = copy.deepcopy(payload)
    collision["e\u0301"] = 1
    collision["é"] = 2
    envelope = sign_envelope(collision, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
    with pytest.raises(AdmissionError, match="NFC collision"):
        verify(material, envelope=envelope)


def test_registry_requires_pinned_root_and_full_quorum(material):
    registry_envelope = sign_envelope(material["registry"], REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    wrong_root, _ = root_material()
    wrong_root = copy.deepcopy(wrong_root)
    wrong_root["keys"][0]["public_key"] = key_material(99, "x", "x", "registry-approval")[0]["public_key"]
    with pytest.raises(AdmissionError, match="quorum"):
        verify_registry_envelope(registry_envelope, wrong_root, material["pin"], NOW)

    fewer = copy.deepcopy(registry_envelope)
    fewer["signatures"] = fewer["signatures"][:-1]
    with pytest.raises(AdmissionError, match="quorum"):
        verify_registry_envelope(fewer, material["trust_root"], material["pin"], NOW)


def test_registry_key_status_is_required_and_inactive_keys_never_satisfy_quorum(material):
    for status in (None, "unknown"):
        registry = copy.deepcopy(material["registry"])
        if status is None:
            del registry["keys"][0]["status"]
        else:
            registry["keys"][0]["status"] = status
        envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
        pin = {"minimum_generation": 7, "registry_sha256": sha256_hex(canonicalize_payload(registry))}
        with pytest.raises(AdmissionError, match="fields are invalid|status is invalid"):
            verify_registry_envelope(envelope, material["trust_root"], pin, NOW)

    for status in ("disabled", "retired", "compromised"):
        registry = copy.deepcopy(material["registry"])
        registry["keys"][0]["status"] = status
        candidate = reissue_registry(material, registry)
        with pytest.raises(AdmissionError, match="quorum"):
            verify(candidate)

    registry_envelope = sign_envelope(
        material["registry"], REGISTRY_PAYLOAD_TYPE, material["root_signers"]
    )
    for status in ("disabled", "retired", "compromised"):
        trust_root = copy.deepcopy(material["trust_root"])
        trust_root["keys"][0]["status"] = status
        with pytest.raises(AdmissionError, match="quorum"):
            verify_registry_envelope(registry_envelope, trust_root, material["pin"], NOW)


def test_registry_generation_hash_and_rotation_chain_fail_closed(material):
    envelope = sign_envelope(material["registry"], REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    with pytest.raises(AdmissionError, match="generation"):
        verify_registry_envelope(envelope, material["trust_root"], {"minimum_generation": 8, "registry_sha256": "d" * 64}, NOW)
    with pytest.raises(AdmissionError, match="same-generation"):
        verify_registry_envelope(envelope, material["trust_root"], {"minimum_generation": 7, "registry_sha256": "d" * 64}, NOW)

    registry = copy.deepcopy(material["registry"])
    registry["generation"] = 8
    registry["previous_registry_sha256"] = "e" * 64
    envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    with pytest.raises(AdmissionError, match="previous registry"):
        verify_registry_envelope(envelope, material["trust_root"], material["pin"], NOW)

    registry["previous_registry_sha256"] = material["pin"]["registry_sha256"]
    envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    snapshot = verify_registry_envelope(envelope, material["trust_root"], material["pin"], NOW)
    assert snapshot.generation == 8


def test_admission_quorum_usage_key_and_artifact_revocation(material):
    fewer = copy.deepcopy(material["envelope"])
    fewer["signatures"] = fewer["signatures"][:-1]
    with pytest.raises(AdmissionError, match="quorum"):
        verify(material, envelope=fewer)

    for mutation in ("wrong-usage", "revoked-key", "revoked-artifact"):
        registry = copy.deepcopy(material["registry"])
        if mutation == "wrong-usage":
            registry["keys"][0]["key_usage"] = "other"
        elif mutation == "revoked-key":
            registry["keys"][0]["revoked_at"] = "2029-05-01T00:00:00Z"
        else:
            registry["revoked_artifacts"] = [material["payload"]["artifact_id"]]
        candidate = reissue_registry(material, registry)
        with pytest.raises(AdmissionError, match="quorum|artifact is revoked"):
            verify(candidate)


def test_registry_rejects_duplicate_principal(material):
    registry = copy.deepcopy(material["registry"])
    registry["keys"][1]["public_key"] = registry["keys"][0]["public_key"]
    envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    pin = {"minimum_generation": 7, "registry_sha256": sha256_hex(canonicalize_payload(registry))}
    with pytest.raises(AdmissionError, match="public keys must be unique"):
        verify_registry_envelope(envelope, material["trust_root"], pin, NOW)


def test_self_reference_and_renewable_consumption_fail(material):
    for mutation in ("self", "consumption"):
        payload = copy.deepcopy(material["payload"])
        if mutation == "self":
            payload["referenced_artifact_ids"] = [payload["artifact_id"]]
        else:
            payload["consumption"] = {"consumed_at": "2029-06-01T00:00:00Z"}
        envelope = sign_envelope(payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
        with pytest.raises(AdmissionError, match="self-reference|must not be consumed"):
            verify(material, envelope=envelope)


def test_one_time_lifecycle_fake_is_idempotent_but_not_transaction_evidence(material):
    registry = copy.deepcopy(material["registry"])
    for key in registry["keys"]:
        key["key_usage"] = "scope-setup"
    registry_hash = sha256_hex(canonicalize_payload(registry))
    registry_envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, material["root_signers"])
    pin = {"minimum_generation": 7, "registry_sha256": registry_hash}
    snapshot = verify_registry_envelope(registry_envelope, material["trust_root"], pin, NOW)
    payload = {
        "schema_version": 1,
        "artifact_type": "real-data-scope-setup",
        "artifact_id": material["payload"]["artifact_id"],
        "lifecycle": "one-time-capability",
        "issued_at": "2029-05-31T00:00:00Z",
        "not_before": "2029-05-31T00:00:00Z",
        "expires_at": "2029-06-30T00:00:00Z",
        "nonce": "00000000000000000000000000000002",
        "target_release_digest": material["payload"]["target_release_digest"],
        "target_commit": material["payload"]["target_commit"],
        "registry": {"generation": 7, "sha256": registry_hash},
        "required_roles": material["payload"]["required_roles"],
        "required_key_usage": "scope-setup",
        "referenced_artifact_ids": [],
        "definition_bundle_sha256": material["payload"]["definition_bundle_sha256"],
        "environment_digest": material["payload"]["environment_digest"],
        "deployment_id": material["payload"]["deployment_id"],
        "owner_ids": material["payload"]["owner_ids"],
        "workspace_id": material["payload"]["workspace_id"],
        "candidate_gate_report": synthetic_reference(
            "gate-1",
            artifact_type="gate-report",
            target_release_digest=material["payload"]["target_release_digest"],
            target_commit=material["payload"]["target_commit"],
            environment_digest=material["payload"]["environment_digest"],
            workspace_id=material["payload"]["workspace_id"],
            gate_id="before_release_candidate",
        ),
        "pilot_readiness_gate_report": synthetic_reference(
            "gate-2",
            artifact_type="gate-report",
            target_release_digest=material["payload"]["target_release_digest"],
            target_commit=material["payload"]["target_commit"],
            environment_digest=material["payload"]["environment_digest"],
            workspace_id=material["payload"]["workspace_id"],
            gate_id="before_pilot_readiness",
        ),
        "shadow_value_decision": synthetic_reference(
            "shadow-1",
            artifact_type="shadow-value-decision",
            target_release_digest=material["payload"]["target_release_digest"],
            target_commit=material["payload"]["target_commit"],
            environment_digest=material["payload"]["environment_digest"],
            workspace_id=material["payload"]["workspace_id"],
            result="go",
        ),
        "allowed_operation": "allocate-workspace-bound-empty-scope-only",
        "maximum_allocations": 1,
        "revocation_id": "revoke-setup-1",
    }
    envelope = sign_envelope(payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
    decision = verify_admission(
        envelope,
        snapshot,
        NOW,
        expected_for(payload),
        reference_verifier=synthetic_reference_verifier,
    )
    fake = LifecycleConsumptionFake()
    first = fake.consume(decision, payload["deployment_id"], payload["workspace_id"], "request-a", NOW)
    assert fake.consume(decision, payload["deployment_id"], payload["workspace_id"], "request-a", NOW) is first
    with pytest.raises(AdmissionError, match="conflicts"):
        fake.consume(decision, payload["deployment_id"], "workspace-other", "request-b", NOW)


def test_scope_setup_constraints_and_reference_port_fail_closed(material):
    registry = copy.deepcopy(material["registry"])
    for key in registry["keys"]:
        key["key_usage"] = "scope-setup"
    candidate = reissue_registry(material, registry)
    payload = copy.deepcopy(material["payload"])
    payload.update(
        artifact_type="real-data-scope-setup",
        lifecycle="one-time-capability",
        required_key_usage="scope-setup",
        registry={"generation": candidate["snapshot"].generation, "sha256": candidate["snapshot"].sha256},
        candidate_gate_report=synthetic_reference(
            "gate-1",
            artifact_type="gate-report",
            target_release_digest=payload["target_release_digest"],
            target_commit=payload["target_commit"],
            environment_digest=payload["environment_digest"],
            workspace_id=payload["workspace_id"],
            gate_id="before_release_candidate",
        ),
        pilot_readiness_gate_report=synthetic_reference(
            "gate-2",
            artifact_type="gate-report",
            target_release_digest=payload["target_release_digest"],
            target_commit=payload["target_commit"],
            environment_digest=payload["environment_digest"],
            workspace_id=payload["workspace_id"],
            gate_id="before_pilot_readiness",
        ),
        shadow_value_decision=synthetic_reference(
            "shadow-1",
            artifact_type="shadow-value-decision",
            target_release_digest=payload["target_release_digest"],
            target_commit=payload["target_commit"],
            environment_digest=payload["environment_digest"],
            workspace_id=payload["workspace_id"],
            result="go",
        ),
        allowed_operation="allocate-workspace-bound-empty-scope-only",
        maximum_allocations=1,
    )
    for field in ("class_ids", "term_ids", "scope_allocation_receipt", "allowed_modules", "evidence_references"):
        payload.pop(field)
    expected = expected_for(payload)

    for field, value, message in (
        ("allowed_operation", "allocate-anything", "operation"),
        ("maximum_allocations", 2, "maximum_allocations"),
    ):
        changed = copy.deepcopy(payload)
        changed[field] = value
        envelope = sign_envelope(changed, ARTIFACT_POLICIES[changed["artifact_type"]].payload_type, material["signers"])
        with pytest.raises(AdmissionError, match=message):
            verify_admission(envelope, candidate["snapshot"], NOW, expected, synthetic_reference_verifier)

    envelope = sign_envelope(payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
    with pytest.raises(AdmissionError, match="reference-verifier port"):
        verify_admission(envelope, candidate["snapshot"], NOW, expected)
    with pytest.raises(AdmissionError, match="invalid result"):
        verify_admission(envelope, candidate["snapshot"], NOW, expected, lambda _r, _e, _t: False)

    stopped = copy.deepcopy(payload)
    stopped["shadow_value_decision"] = synthetic_reference(
        "shadow-stop-setup",
        artifact_type="shadow-value-decision",
        target_release_digest=payload["target_release_digest"],
        target_commit=payload["target_commit"],
        environment_digest=payload["environment_digest"],
        workspace_id=payload["workspace_id"],
        result="stop",
    )
    stopped_envelope = sign_envelope(
        stopped, ARTIFACT_POLICIES[stopped["artifact_type"]].payload_type, material["signers"]
    )
    with pytest.raises(AdmissionError, match="shadow go"):
        verify_admission(
            stopped_envelope, candidate["snapshot"], NOW, expected, synthetic_reference_verifier
        )


def test_admission_nested_reference_bindings_fail_closed(material):
    payload = copy.deepcopy(material["payload"])
    payload["scope_allocation_receipt"] = synthetic_reference(
        "receipt-synthetic-wrong-workspace",
        artifact_type="scope-allocation-receipt",
        target_release_digest=payload["target_release_digest"],
        target_commit=payload["target_commit"],
        environment_digest=payload["environment_digest"],
        deployment_id=payload["deployment_id"],
        workspace_id="workspace-other",
        owner_ids=payload["owner_ids"],
        reserved_class_ids=payload["class_ids"],
        reserved_term_ids=payload["term_ids"],
    )
    envelope = sign_envelope(payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"])
    with pytest.raises(AdmissionError, match="binding mismatch: workspace_id"):
        verify(material, envelope=envelope)

    with pytest.raises(AdmissionError, match="invalid result"):
        verify(material, reference_verifier=lambda _r, _e, _t: False)


def test_candidate_and_pilot_gate_slots_cannot_reuse_one_verified_report(material):
    payload = copy.deepcopy(material["payload"])
    payload["evidence_references"]["pilot_readiness_gate_report"] = copy.deepcopy(
        payload["evidence_references"]["candidate_gate_report"]
    )
    envelope = sign_envelope(
        payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"]
    )
    with pytest.raises(AdmissionError, match="pilot_readiness|gate_id|distinct"):
        verify(material, envelope=envelope)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("class", "reserved_class_ids"),
        ("term", "reserved_term_ids"),
        ("owner", "owner_ids"),
        ("module", "unknown module"),
        ("type", "metadata mismatch"),
        ("digest", "metadata mismatch"),
        ("shadow", "shadow go"),
    ],
)
def test_admission_verified_reference_scope_type_and_result_fail_closed(material, mutation, message):
    payload = copy.deepcopy(material["payload"])
    if mutation == "class":
        payload["class_ids"] = ["class-not-allocated"]
    elif mutation == "term":
        payload["term_ids"] = ["term-not-allocated"]
    elif mutation == "owner":
        payload["owner_ids"] = ["owner-not-approved"]
    elif mutation == "module":
        payload["allowed_modules"] = ["roster", "unknown-module"]
    elif mutation == "type":
        payload["scope_allocation_receipt"] = synthetic_reference(
            "gate-wrongly-used-as-receipt",
            artifact_type="gate-report",
            target_release_digest=payload["target_release_digest"],
            target_commit=payload["target_commit"],
            environment_digest=payload["environment_digest"],
            deployment_id=payload["deployment_id"],
            workspace_id=payload["workspace_id"],
            gate_id="before_release_candidate",
        )
    elif mutation == "digest":
        payload["scope_allocation_receipt"]["sha256"] = "0" * 64
    else:
        payload["evidence_references"]["shadow_value_decision"] = synthetic_reference(
            "shadow-stop-admission",
            artifact_type="shadow-value-decision",
            target_release_digest=payload["target_release_digest"],
            target_commit=payload["target_commit"],
            environment_digest=payload["environment_digest"],
            workspace_id=payload["workspace_id"],
            result="stop",
        )
    envelope = sign_envelope(
        payload, ARTIFACT_POLICIES[payload["artifact_type"]].payload_type, material["signers"]
    )
    with pytest.raises(AdmissionError, match=message):
        verify(material, envelope=envelope)


def test_reference_verifier_returned_payload_must_match_reference_digest(material):
    def mismatched_payload(reference, expected, expected_type):
        verified = synthetic_reference_verifier(reference, expected, expected_type)
        return replace(verified, canonical_payload=b"{}")

    with pytest.raises(AdmissionError, match="verified payload digest mismatch"):
        verify(material, reference_verifier=mismatched_payload)

    def forged_roles(reference, expected, expected_type):
        verified = synthetic_reference_verifier(reference, expected, expected_type)
        return replace(verified, verified_roles=frozenset({"attacker-role"}))

    with pytest.raises(AdmissionError, match="role quorum mismatch"):
        verify(material, reference_verifier=forged_roles)


def test_shadow_result_receipt_content_and_digest_formats_are_enforced(material):
    shadow_fields = {
        "environment_digest": material["payload"]["environment_digest"],
        "workspace_id": material["payload"]["workspace_id"],
        "pilot_owner_id": "owner-synthetic-001",
        "measurement_protocol_sha256": "1" * 64,
        "result": "maybe",
        "cost_summary_sha256": "2" * 64,
        "evidence_index_sha256": "3" * 64,
    }
    with pytest.raises(AdmissionError, match="result is invalid"):
        issue_policy_artifact(material, "shadow-value-decision", "shadow-invalid-001", shadow_fields)

    receipt_fields = {
        "setup_artifact_id": "setup-synthetic-001",
        "deployment_id": material["payload"]["deployment_id"],
        "owner_ids": material["payload"]["owner_ids"],
        "workspace_id": material["payload"]["workspace_id"],
        "reserved_class_ids": [{"student": "forbidden"}],
        "reserved_term_ids": ["term-synthetic-001"],
        "environment_digest": material["payload"]["environment_digest"],
        "ledger_sequence": 1,
        "ledger_entry_sha256": "4" * 64,
        "allocated_at": "2029-05-31T01:00:00Z",
    }
    with pytest.raises(AdmissionError, match="forbidden business fields"):
        issue_policy_artifact(
            material, "scope-allocation-receipt", "receipt-synthetic-forbidden", receipt_fields
        )

    with pytest.raises(AdmissionError, match="lowercase hexadecimal"):
        issue_policy_artifact(
            material,
            "state-transition",
            "state-transition-invalid-commit",
            {
                "state_type": "release-1-task-state",
                "state_sha256": "5" * 64,
                "definition_bundle_sha256": material["payload"]["definition_bundle_sha256"],
                "target_commit": "z" * 40,
            },
        )


def test_mutable_state_requires_verified_transition_and_exact_content_hash(material):
    state = {
        "schema_version": 1,
        "release": "class-os-r1",
        "tasks": [{"task_id": "T-REVAL-019", "status": "planned"}],
    }
    state_hash = sha256_hex(canonicalize_payload(state))
    transition_fields = {
        "state_type": "release-1-task-state",
        "state_sha256": state_hash,
        "definition_bundle_sha256": material["payload"]["definition_bundle_sha256"],
    }
    _payload, decision, expected = issue_policy_artifact(
        material, "state-transition", "state-transition-synthetic-001", transition_fields
    )
    state["state_transition_artifact"] = {
        "artifact_id": decision.artifact_id,
        "artifact_uri": "synthetic://signed-artifacts/state-transition-synthetic-001.dsse.json",
    }
    assert verify_mutable_state_binding(state, decision, expected) == state_hash

    changed = copy.deepcopy(state)
    changed["tasks"][0]["status"] = "green"
    with pytest.raises(AdmissionError, match="state hash mismatch"):
        verify_mutable_state_binding(changed, decision, expected)


def test_reference_graph_rejects_cycle_and_unresolved_reference():
    with pytest.raises(AdmissionError, match="cycle"):
        validate_reference_graph(
            [
                {"artifact_id": "definition", "referenced_artifact_ids": ["state"]},
                {"artifact_id": "state", "referenced_artifact_ids": ["definition"]},
            ]
        )
    with pytest.raises(AdmissionError, match="unresolved"):
        validate_reference_graph([{"artifact_id": "evidence", "referenced_artifact_ids": ["missing"]}])


def test_definition_state_and_evidence_paths_are_structurally_separate():
    policy = yaml.safe_load((REPO_ROOT / ".ai/gates/signed-artifact-policy.yaml").read_text(encoding="utf-8"))
    manifests = set(policy["definition_bundle"]["manifests"])
    assert policy["definition_bundle"]["approval_state"] not in manifests
    assert not any("state.yaml" in path for path in manifests)
    assert policy["mutable_state_signing"]["inline_signature_envelope_is_forbidden"] is True
    assert policy["production_authorization"] is False
