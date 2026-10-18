from __future__ import annotations

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from reference_resolver import InMemoryIdentityLedger, ReferenceResolver, RootedArtifactStore
import reference_resolver as resolver_module
from signature_envelope import (
    ARTIFACT_POLICIES,
    REGISTRY_PAYLOAD_TYPE,
    AdmissionError,
    ExpectedContext,
    canonicalize_payload,
    sha256_hex,
    sign_envelope,
    verify_admission,
    verify_registry_envelope,
)


NOW = datetime(2029, 6, 1, tzinfo=UTC)
TARGET_RELEASE = "sha256:" + "b" * 64
TARGET_COMMIT = "0123456789abcdef0123456789abcdef01234567"
DEFINITION_BUNDLE = "c" * 64
ENVIRONMENT = "sha256:" + "d" * 64


def key_record(seed: int, key_id: str, role: str, usage: str):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return (
        {
            "key_id": key_id,
            "signer_id": f"synthetic-{role}-{seed}",
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


@pytest.fixture
def resolver_material(tmp_path: Path, request):
    options = getattr(request, "param", {})
    root_keys, root_signers = [], []
    for seed, role in zip((21, 22, 23), ("offline-root", "security", "operations"), strict=True):
        record, private = key_record(seed, f"root-{role}", role, "registry-approval")
        root_keys.append(record)
        root_signers.append((record["key_id"], private))

    artifact_key, artifact_private = key_record(
        31, "gate-release-verifier", "release-verifier", "gate-report"
    )
    catalog_key, catalog_private = key_record(
        39, "catalog-release-verifier", "release-verifier", "reference-catalog"
    )
    shadow_keys, shadow_signers = [], []
    for seed, role in zip((32, 33, 34), ("product", "pilot-owner", "release-verifier"), strict=True):
        record, private = key_record(seed, f"shadow-{role}", role, "shadow-value-decision")
        shadow_keys.append(record)
        shadow_signers.append((record["key_id"], private))
    setup_keys, setup_signers = [], []
    for seed, role in zip((35, 36, 37, 38), ("product", "privacy", "security", "operations"), strict=True):
        record, private = key_record(seed, f"setup-{role}", role, "scope-setup")
        setup_keys.append(record)
        setup_signers.append((record["key_id"], private))
    registry = {
        "schema_version": 1,
        "generation": 7,
        "previous_registry_sha256": "a" * 64,
        "issued_at": "2029-01-01T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "issued_artifacts": [
            "gate-synthetic-001",
            "gate-synthetic-002",
            "shadow-synthetic-001",
            "setup-synthetic-001",
            "catalog-synthetic-001",
        ],
        "revoked_artifacts": options.get("revoked_artifacts", []),
        "keys": [artifact_key, catalog_key, *shadow_keys, *setup_keys],
    }
    registry_hash = sha256_hex(canonicalize_payload(registry))
    root = {"schema_version": 1, "keys": root_keys}
    registry_envelope = sign_envelope(registry, REGISTRY_PAYLOAD_TYPE, root_signers)
    snapshot = verify_registry_envelope(
        registry_envelope,
        root,
        {"minimum_generation": 7, "registry_sha256": registry_hash},
        NOW,
    )

    def issue(
        artifact_id: str,
        nonce: str,
        *,
        gate_id: str = "before_release_candidate",
        generic_refs: list[str] | None = None,
        generic_bindings: list[dict[str, str]] | None = None,
        catalog_reference: dict[str, str] | None = None,
        expires_at: str = "2029-06-30T00:00:00Z",
    ):
        payload = {
            "schema_version": 1,
            "artifact_type": "gate-report",
            "artifact_id": artifact_id,
            "lifecycle": "reusable-attestation",
            "issued_at": "2029-05-31T00:00:00Z",
            "not_before": "2029-05-31T00:00:00Z",
            "expires_at": expires_at,
            "nonce": nonce,
            "target_release_digest": TARGET_RELEASE,
            "target_commit": TARGET_COMMIT,
            "registry": {"generation": 7, "sha256": registry_hash},
            "required_roles": ["release-verifier"],
            "required_key_usage": "gate-report",
            "referenced_artifact_ids": generic_refs or [],
            "artifact_uri": f"evidence://{artifact_id}/report.json",
            "sha256": "e" * 64,
            "produced_at": "2029-05-31T00:00:00Z",
            "gate_id": gate_id,
            "gate_definition_sha256": "f" * 64,
            "definition_bundle_sha256": DEFINITION_BUNDLE,
            "verifier_digest": "sha256:" + "1" * 64,
            "environment_digest": ENVIRONMENT,
        }
        if generic_bindings is not None:
            payload["reference_bindings"] = generic_bindings
        if catalog_reference is not None:
            payload["reference_catalog"] = catalog_reference
        envelope = sign_envelope(
            payload,
            ARTIFACT_POLICIES["gate-report"].payload_type,
            [(artifact_key["key_id"], artifact_private)],
        )
        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        filename = f"{artifact_id}.dsse.json"
        (tmp_path / filename).write_bytes(raw)
        reference = {
            "artifact_id": artifact_id,
            "artifact_uri": f"classos-artifact://local/{filename}",
            "sha256": sha256_hex(canonicalize_payload(payload)),
            "gate_id": gate_id,
            "gate_definition_sha256": payload["gate_definition_sha256"],
            "definition_bundle_sha256": payload["definition_bundle_sha256"],
            "verifier_digest": payload["verifier_digest"],
            "target_release_digest": payload["target_release_digest"],
            "target_commit": payload["target_commit"],
            "environment_digest": payload["environment_digest"],
        }
        return payload, envelope, reference

    def issue_catalog(entries: list[dict[str, str]], *, expires_at: str = "2029-06-30T00:00:00Z"):
        payload = {
            "schema_version": 1,
            "artifact_type": "reference-catalog",
            "artifact_id": "catalog-synthetic-001",
            "lifecycle": "reusable-attestation",
            "issued_at": "2029-05-31T00:00:00Z",
            "not_before": "2029-05-31T00:00:00Z",
            "expires_at": expires_at,
            "nonce": "00000000000000000000000000000009",
            "target_release_digest": TARGET_RELEASE,
            "target_commit": TARGET_COMMIT,
            "registry": {"generation": 7, "sha256": registry_hash},
            "required_roles": ["release-verifier"],
            "required_key_usage": "reference-catalog",
            "referenced_artifact_ids": [],
            "entries": entries,
        }
        envelope = sign_envelope(
            payload,
            ARTIFACT_POLICIES["reference-catalog"].payload_type,
            [(catalog_key["key_id"], catalog_private)],
        )
        (tmp_path / "catalog-synthetic-001.dsse.json").write_text(
            json.dumps(envelope, separators=(",", ":")), encoding="utf-8", newline="\n"
        )
        return payload, envelope, {
            "artifact_id": "catalog-synthetic-001",
            "artifact_uri": "classos-artifact://local/catalog-synthetic-001.dsse.json",
            "sha256": sha256_hex(canonicalize_payload(payload)),
        }

    def issue_shadow(
        artifact_id: str = "shadow-synthetic-001",
        nonce: str = "00000000000000000000000000000003",
    ):
        payload = {
            "schema_version": 1,
            "artifact_type": "shadow-value-decision",
            "artifact_id": artifact_id,
            "lifecycle": "reusable-attestation",
            "issued_at": "2029-05-31T00:00:00Z",
            "not_before": "2029-05-31T00:00:00Z",
            "expires_at": "2029-06-30T00:00:00Z",
            "nonce": nonce,
            "target_release_digest": TARGET_RELEASE,
            "target_commit": TARGET_COMMIT,
            "registry": {"generation": 7, "sha256": registry_hash},
            "required_roles": ["pilot-owner", "product", "release-verifier"],
            "required_key_usage": "shadow-value-decision",
            "referenced_artifact_ids": [],
            "environment_digest": ENVIRONMENT,
            "workspace_id": "workspace-synthetic-001",
            "pilot_owner_id": "owner-synthetic-001",
            "measurement_protocol_sha256": "4" * 64,
            "result": "go",
            "cost_summary_sha256": "5" * 64,
            "evidence_index_sha256": "6" * 64,
        }
        envelope = sign_envelope(
            payload,
            ARTIFACT_POLICIES["shadow-value-decision"].payload_type,
            shadow_signers,
        )
        filename = f"{artifact_id}.shadow.dsse.json"
        (tmp_path / filename).write_text(
            json.dumps(envelope, separators=(",", ":")), encoding="utf-8", newline="\n"
        )
        return {
            "artifact_id": payload["artifact_id"],
            "artifact_uri": f"classos-artifact://local/{filename}",
            "sha256": sha256_hex(canonicalize_payload(payload)),
            "target_release_digest": TARGET_RELEASE,
            "target_commit": TARGET_COMMIT,
            "environment_digest": ENVIRONMENT,
            "workspace_id": payload["workspace_id"],
        }

    def issue_setup():
        _candidate_payload, _candidate_envelope, candidate = issue(
            "gate-synthetic-001",
            "00000000000000000000000000000001",
            gate_id="before_release_candidate",
        )
        _pilot_payload, _pilot_envelope, pilot = issue(
            "gate-synthetic-002",
            "00000000000000000000000000000002",
            gate_id="before_pilot_readiness",
        )
        shadow = issue_shadow()
        payload = {
            "schema_version": 1,
            "artifact_type": "real-data-scope-setup",
            "artifact_id": "setup-synthetic-001",
            "lifecycle": "one-time-capability",
            "issued_at": "2029-05-31T00:00:00Z",
            "not_before": "2029-05-31T00:00:00Z",
            "expires_at": "2029-06-30T00:00:00Z",
            "nonce": "00000000000000000000000000000004",
            "target_release_digest": TARGET_RELEASE,
            "target_commit": TARGET_COMMIT,
            "registry": {"generation": 7, "sha256": registry_hash},
            "required_roles": ["operations", "privacy", "product", "security"],
            "required_key_usage": "scope-setup",
            "referenced_artifact_ids": [],
            "definition_bundle_sha256": DEFINITION_BUNDLE,
            "environment_digest": ENVIRONMENT,
            "deployment_id": "deployment-synthetic-001",
            "owner_ids": ["owner-synthetic-001"],
            "workspace_id": "workspace-synthetic-001",
            "candidate_gate_report": candidate,
            "pilot_readiness_gate_report": pilot,
            "shadow_value_decision": shadow,
            "allowed_operation": "allocate-workspace-bound-empty-scope-only",
            "maximum_allocations": 1,
            "revocation_id": "revoke-setup-synthetic-001",
        }
        envelope = sign_envelope(
            payload,
            ARTIFACT_POLICIES["real-data-scope-setup"].payload_type,
            setup_signers,
        )
        filename = "setup-synthetic-001.dsse.json"
        (tmp_path / filename).write_text(
            json.dumps(envelope, separators=(",", ":")), encoding="utf-8", newline="\n"
        )
        reference = {
            "artifact_id": payload["artifact_id"],
            "artifact_uri": f"classos-artifact://local/{filename}",
            "sha256": sha256_hex(canonicalize_payload(payload)),
        }
        expected_setup = ExpectedContext(
            artifact_type="real-data-scope-setup",
            target_release_digest=TARGET_RELEASE,
            target_commit=TARGET_COMMIT,
            definition_bundle_sha256=DEFINITION_BUNDLE,
            environment_digest=ENVIRONMENT,
            deployment_id=payload["deployment_id"],
            workspace_id=payload["workspace_id"],
        )
        return payload, reference, expected_setup

    expected = ExpectedContext(
        artifact_type="gate-report",
        target_release_digest=TARGET_RELEASE,
        target_commit=TARGET_COMMIT,
        definition_bundle_sha256=DEFINITION_BUNDLE,
        environment_digest=ENVIRONMENT,
    )
    ledger = InMemoryIdentityLedger()
    resolver = ReferenceResolver(
        RootedArtifactStore(tmp_path, store_id="local", max_bytes=64 * 1024),
        snapshot,
        NOW,
        identity_ledger=ledger,
        max_depth=8,
        max_nodes=32,
    )
    return {
        "root": tmp_path,
        "snapshot": snapshot,
        "issue": issue,
        "issue_catalog": issue_catalog,
        "issue_shadow": issue_shadow,
        "issue_setup": issue_setup,
        "expected": expected,
        "ledger": ledger,
        "resolver": resolver,
    }


def test_concrete_store_fetch_digest_dsse_and_policy_verification(resolver_material):
    payload, _envelope, reference = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    verified = resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")
    assert verified.artifact_id == payload["artifact_id"]
    assert verified.artifact_type == "gate-report"
    assert verified.digest == reference["sha256"]
    assert json.loads(verified.canonical_payload) == payload
    assert verified.verified_roles == frozenset({"release-verifier"})


def test_generic_reference_requires_signed_catalog_and_complete_closure(resolver_material):
    _child_payload, _child_envelope, child = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )
    _unsigned_closure_payload, _unsigned_closure_envelope, unbound_parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
    )
    with pytest.raises(AdmissionError, match="bindings|catalog"):
        resolver_material["resolver"](unbound_parent, resolver_material["expected"], "gate-report")

    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"](
        [{"artifact_id": child["artifact_id"], "artifact_uri": child["artifact_uri"]}]
    )
    _parent_payload, parent_envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": child["artifact_id"], "artifact_type": "gate-report",
                           "sha256": child["sha256"]}],
        catalog_reference=catalog,
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW,
        identity_ledger=InMemoryIdentityLedger(),
    )
    assert resolver(parent, resolver_material["expected"], "gate-report").artifact_id == parent["artifact_id"]
    with pytest.raises(AdmissionError, match="closure verifier"):
        verify_admission(parent_envelope, resolver_material["snapshot"], NOW,
                         resolver_material["expected"])
    assert verify_admission(parent_envelope, resolver_material["snapshot"], NOW,
                            resolver_material["expected"], resolver).eligible is True

    class WrongParentDigest:
        def __call__(self, reference, expected, artifact_type):
            return resolver(reference, expected, artifact_type)

        def resolve_generic_closure(self, *args):
            return replace(resolver.resolve_generic_closure(*args),
                           parent_payload_sha256="0" * 64)

    with pytest.raises(AdmissionError, match="closure result"):
        verify_admission(parent_envelope, resolver_material["snapshot"], NOW,
                         resolver_material["expected"], WrongParentDigest())


def test_generic_catalog_missing_tampered_and_digest_fail_closed(resolver_material):
    _child_payload, _child_envelope, child = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )
    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"]([])
    def issue_parent(digest=child["sha256"], catalog_ref=catalog):
        return resolver_material["issue"](
            "gate-synthetic-001", "00000000000000000000000000000001",
            generic_refs=["gate-synthetic-002"],
            generic_bindings=[{"artifact_id": child["artifact_id"],
                               "artifact_type": "gate-report", "sha256": digest}],
            catalog_reference=catalog_ref,
        )[2]
    def fresh_resolver():
        return ReferenceResolver(
            RootedArtifactStore(resolver_material["root"], store_id="local"),
            resolver_material["snapshot"], NOW, identity_ledger=InMemoryIdentityLedger(),
        )
    with pytest.raises(AdmissionError, match="unresolved"):
        fresh_resolver()(issue_parent(), resolver_material["expected"], "gate-report")

    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"](
        [{"artifact_id": child["artifact_id"], "artifact_uri": child["artifact_uri"]}]
    )
    with pytest.raises(AdmissionError, match="digest"):
        fresh_resolver()(issue_parent(digest="0" * 64, catalog_ref=catalog),
                 resolver_material["expected"], "gate-report")

    parent = issue_parent(catalog_ref=catalog)
    catalog_path = resolver_material["root"] / "catalog-synthetic-001.dsse.json"
    envelope = json.loads(catalog_path.read_text(encoding="utf-8"))
    envelope["signatures"][0]["sig"] = "AA" + envelope["signatures"][0]["sig"][2:]
    catalog_path.write_text(json.dumps(envelope), encoding="utf-8", newline="\n")
    with pytest.raises(AdmissionError):
        fresh_resolver()(parent, resolver_material["expected"], "gate-report")


def test_parent_digest_binding_rejects_validly_signed_catalog_swap(resolver_material):
    _child_payload, _child_envelope, child = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )
    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"](
        [{"artifact_id": child["artifact_id"], "artifact_uri": child["artifact_uri"]}]
    )
    _parent_payload, _parent_envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": child["artifact_id"],
                           "artifact_type": "gate-report", "sha256": child["sha256"]}],
        catalog_reference=catalog,
    )
    resolver_material["issue_catalog"]([])
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW, identity_ledger=InMemoryIdentityLedger(),
    )
    with pytest.raises(AdmissionError, match="digest"):
        resolver(parent, resolver_material["expected"], "gate-report")


@pytest.mark.parametrize(
    ("resolver_material", "expires_catalog", "expires_target", "expected_error"),
    [
        ({"revoked_artifacts": ["catalog-synthetic-001"]}, False, False, "revoked"),
        ({"revoked_artifacts": ["gate-synthetic-002"]}, False, False, "revoked"),
        ({}, True, False, "expired"),
        ({}, False, True, "expired"),
    ],
    indirect=["resolver_material"],
)
def test_generic_closure_rejects_revoked_or_expired_catalog_and_target(
    resolver_material, expires_catalog, expires_target, expected_error
):
    _child_payload, _child_envelope, child = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002",
        expires_at="2029-05-31T12:00:00Z" if expires_target else "2029-06-30T00:00:00Z",
    )
    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"](
        [{"artifact_id": child["artifact_id"], "artifact_uri": child["artifact_uri"]}],
        expires_at="2029-05-31T12:00:00Z" if expires_catalog else "2029-06-30T00:00:00Z",
    )
    _parent_payload, _parent_envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": child["artifact_id"],
                           "artifact_type": "gate-report", "sha256": child["sha256"]}],
        catalog_reference=catalog,
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW, identity_ledger=InMemoryIdentityLedger(),
    )
    with pytest.raises(AdmissionError, match=expected_error):
        resolver(parent, resolver_material["expected"], "gate-report")


def test_concurrent_generic_closure_keeps_root_sessions_isolated(resolver_material):
    _child_payload, _child_envelope, child = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )
    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"](
        [{"artifact_id": child["artifact_id"], "artifact_uri": child["artifact_uri"]}]
    )
    _parent_payload, _parent_envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": child["artifact_id"],
                           "artifact_type": "gate-report", "sha256": child["sha256"]}],
        catalog_reference=catalog,
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW, identity_ledger=InMemoryIdentityLedger(),
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: resolver(parent, resolver_material["expected"], "gate-report").artifact_id,
            range(12),
        ))
    assert results == ["gate-synthetic-001"] * 12


@pytest.mark.parametrize(
    "bad_entry",
    [
        {"artifact_id": "gate-synthetic-002", "artifact_type": [],
         "artifact_uri": "classos-artifact://local/gate-synthetic-002.dsse.json"},
        {"artifact_id": "gate-synthetic-002", "artifact_uri": ""},
        {"artifact_id": "gate-synthetic-002",
         "artifact_uri": "classos-artifact://local/gate-synthetic-002.dsse.json",
         "unapproved_field": "x"},
    ],
)
def test_signed_catalog_rejects_malformed_entries(resolver_material, bad_entry):
    _payload, _envelope, catalog = resolver_material["issue_catalog"]([bad_entry])
    _payload, _envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": "gate-synthetic-002",
                           "artifact_type": "gate-report", "sha256": "0" * 64}],
        catalog_reference=catalog,
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW,
        identity_ledger=InMemoryIdentityLedger(),
    )
    with pytest.raises(AdmissionError, match="catalog"):
        resolver(parent, resolver_material["expected"], "gate-report")


def test_signed_catalog_cannot_be_a_type_authority(resolver_material):
    _child_payload, _child_envelope, child = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )
    entry = {field: child[field] for field in ("artifact_id", "artifact_uri")}
    _payload, _envelope, catalog = resolver_material["issue_catalog"]([entry])
    _parent_payload, _parent_envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": child["artifact_id"],
                           "artifact_type": "shadow-value-decision", "sha256": child["sha256"]}],
        catalog_reference=catalog,
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW,
        identity_ledger=InMemoryIdentityLedger(),
    )
    with pytest.raises(AdmissionError, match="payload type|artifact type|lifecycle"):
        resolver(parent, resolver_material["expected"], "gate-report")


def test_same_issued_id_with_alternative_valid_type_cannot_replace_parent_binding(
    resolver_material,
):
    _gate_payload, _gate_envelope, gate = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )
    shadow = resolver_material["issue_shadow"](
        "gate-synthetic-002", "00000000000000000000000000000008"
    )
    _catalog_payload, _catalog_envelope, catalog = resolver_material["issue_catalog"](
        [{"artifact_id": gate["artifact_id"], "artifact_uri": shadow["artifact_uri"]}]
    )
    _parent_payload, _parent_envelope, parent = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001",
        generic_refs=["gate-synthetic-002"],
        generic_bindings=[{"artifact_id": gate["artifact_id"],
                           "artifact_type": "gate-report", "sha256": gate["sha256"]}],
        catalog_reference=catalog,
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"], NOW, identity_ledger=InMemoryIdentityLedger(),
    )
    with pytest.raises(AdmissionError, match="payload type"):
        resolver(parent, resolver_material["expected"], "gate-report")


def test_concrete_scope_setup_resolves_distinct_release_level_gates_and_workspace_shadow(
    resolver_material,
):
    payload, reference, expected = resolver_material["issue_setup"]()
    verified = resolver_material["resolver"](
        reference, expected, "real-data-scope-setup"
    )
    assert verified.artifact_id == payload["artifact_id"]
    assert verified.artifact_type == "real-data-scope-setup"


@pytest.mark.parametrize(
    "uri",
    [
        "file:///etc/passwd",
        "https://attacker.invalid/report.dsse.json",
        "classos-artifact://other/gate-synthetic-001.dsse.json",
        "classos-artifact://local/../outside.dsse.json",
        "classos-artifact://local/%2e%2e/outside.dsse.json",
        "classos-artifact://local/C:%5CWindows%5Cwin.ini",
    ],
)
def test_store_rejects_unapproved_scheme_authority_and_traversal(resolver_material, uri):
    _payload, _envelope, reference = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    reference["artifact_uri"] = uri
    with pytest.raises(AdmissionError, match="artifact URI"):
        resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")


def test_digest_signature_and_expected_type_mutations_fail(resolver_material):
    _payload, envelope, reference = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    wrong_digest = copy.deepcopy(reference)
    wrong_digest["sha256"] = "0" * 64
    with pytest.raises(AdmissionError, match="digest"):
        resolver_material["resolver"](wrong_digest, resolver_material["expected"], "gate-report")

    path = resolver_material["root"] / "gate-synthetic-001.dsse.json"
    mutated = copy.deepcopy(envelope)
    mutated["signatures"][0]["sig"] = "AA" + mutated["signatures"][0]["sig"][2:]
    path.write_text(json.dumps(mutated), encoding="utf-8", newline="\n")
    with pytest.raises(AdmissionError):
        resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")

    resolver_material["issue"]("gate-synthetic-001", "00000000000000000000000000000001")
    with pytest.raises(AdmissionError, match="artifact type|payload type|unsupported"):
        resolver_material["resolver"](reference, resolver_material["expected"], "shadow-value-decision")


def test_duplicate_json_invalid_utf8_and_size_limit_fail_closed(resolver_material):
    _payload, envelope, reference = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    path = resolver_material["root"] / "gate-synthetic-001.dsse.json"
    raw = json.dumps(envelope, separators=(",", ":"))
    path.write_text(raw[:-1] + ',"payloadType":"duplicate"}', encoding="utf-8", newline="\n")
    with pytest.raises(AdmissionError, match="duplicate JSON"):
        resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")

    path.write_bytes(b"\xff\xfe")
    with pytest.raises(AdmissionError, match="UTF-8"):
        resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")

    resolver_material["issue"]("gate-synthetic-001", "00000000000000000000000000000001")
    small = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local", max_bytes=8),
        resolver_material["snapshot"],
        NOW,
        identity_ledger=InMemoryIdentityLedger(),
    )
    with pytest.raises(AdmissionError, match="size limit"):
        small(reference, resolver_material["expected"], "gate-report")


def test_artifact_id_and_nonce_collision_fail_even_with_valid_signatures(resolver_material):
    _payload, _envelope, first = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    resolver_material["resolver"](first, resolver_material["expected"], "gate-report")

    _payload, _envelope, changed_same_id = resolver_material["issue"](
        "gate-synthetic-001",
        "00000000000000000000000000000002",
        gate_id="changed-gate",
    )
    with pytest.raises(AdmissionError, match="artifact id collision"):
        resolver_material["resolver"](
            changed_same_id, resolver_material["expected"], "gate-report"
        )

    _payload, _envelope, same_nonce = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000001"
    )
    with pytest.raises(AdmissionError, match="nonce collision"):
        resolver_material["resolver"](same_nonce, resolver_material["expected"], "gate-report")


def test_missing_identity_ledger_fails_closed(resolver_material):
    _payload, _envelope, reference = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    resolver = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"],
        NOW,
        identity_ledger=None,
    )
    with pytest.raises(AdmissionError, match="identity ledger"):
        resolver(reference, resolver_material["expected"], "gate-report")


def test_recursive_reference_cycle_and_graph_limits_fail_closed(
    resolver_material, monkeypatch
):
    _payload, _envelope, first = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    _payload, _envelope, second = resolver_material["issue"](
        "gate-synthetic-002", "00000000000000000000000000000002"
    )

    def cycle_verify(_envelope, _snapshot, _now, expected, reference_verifier):
        return reference_verifier(first, expected, "gate-report")

    monkeypatch.setattr(resolver_module, "verify_admission", cycle_verify)
    with pytest.raises(AdmissionError, match="cycle"):
        resolver_material["resolver"](first, resolver_material["expected"], "gate-report")

    def nested_verify(_envelope, _snapshot, _now, expected, reference_verifier):
        return reference_verifier(second, expected, "gate-report")

    monkeypatch.setattr(resolver_module, "verify_admission", nested_verify)
    depth_limited = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"],
        NOW,
        identity_ledger=InMemoryIdentityLedger(),
        max_depth=1,
        max_nodes=32,
    )
    with pytest.raises(AdmissionError, match="depth limit"):
        depth_limited(first, resolver_material["expected"], "gate-report")

    node_limited = ReferenceResolver(
        RootedArtifactStore(resolver_material["root"], store_id="local"),
        resolver_material["snapshot"],
        NOW,
        identity_ledger=InMemoryIdentityLedger(),
        max_depth=8,
        max_nodes=1,
    )
    with pytest.raises(AdmissionError, match="node limit"):
        node_limited(first, resolver_material["expected"], "gate-report")


def test_store_rejects_symlink_escape_when_platform_allows_symlinks(
    resolver_material, tmp_path
):
    outside = tmp_path.parent / "outside.dsse.json"
    outside.write_text("{}", encoding="utf-8")
    link = resolver_material["root"] / "linked.dsse.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    reference = {
        "artifact_id": "gate-synthetic-001",
        "artifact_uri": "classos-artifact://local/linked.dsse.json",
        "sha256": "0" * 64,
    }
    with pytest.raises(AdmissionError, match="symlink"):
        resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_store_rejects_native_junction_even_when_target_stays_inside_root(
    resolver_material,
):
    import subprocess

    root = resolver_material["root"]
    target = root / "target"
    target.mkdir()
    (target / "artifact.dsse.json").write_text("{}", encoding="utf-8")
    junction = root / "junction"
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip("junction creation unavailable on this Windows host")
    with pytest.raises(AdmissionError, match="reparse"):
        resolver_module._windows_open_no_follow(junction)
    with pytest.raises(AdmissionError, match="path is invalid"):
        resolver_material["resolver"]._store.fetch(
            "classos-artifact://local/junction/artifact.dsse.json"
        )


def test_artifact_store_rejects_nested_uri_on_every_platform(resolver_material):
    with pytest.raises(AdmissionError, match="path is invalid"):
        resolver_material["resolver"]._store.fetch(
            "classos-artifact://local/nested/artifact.dsse.json"
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction race contract")
def test_final_file_replaced_by_junction_after_precheck_is_rejected(
    resolver_material, monkeypatch
):
    import subprocess

    root = resolver_material["root"]
    candidate = root / "artifact.dsse.json"
    candidate.write_text("{}", encoding="utf-8")
    backup = root / "original.backup"
    target = root / "replacement-target"
    target.mkdir()
    real_open = resolver_module._windows_open_no_follow

    def replace_then_open(path):
        candidate.rename(backup)
        try:
            made = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(candidate), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if made.returncode != 0:
                pytest.skip("junction creation unavailable on this Windows host")
            return real_open(path)
        finally:
            if candidate.is_junction():
                candidate.rmdir()
            backup.rename(candidate)

    monkeypatch.setattr(resolver_module, "_windows_open_no_follow", replace_then_open)
    with pytest.raises(AdmissionError, match="opened artifact is a reparse point"):
        resolver_material["resolver"]._store.fetch(
            "classos-artifact://local/artifact.dsse.json"
        )


def test_opened_file_descriptor_must_match_the_checked_store_path(
    resolver_material, tmp_path, monkeypatch
):
    _payload, _envelope, reference = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    outside = tmp_path.parent / "attacker-envelope.json"
    outside.write_bytes(b"ATTACKER")
    if os.name == "nt":
        real_open = resolver_module._windows_open_no_follow

        def substituted_open(_path):
            return real_open(outside)

        monkeypatch.setattr(resolver_module, "_windows_open_no_follow", substituted_open)
    else:
        real_open = resolver_module.os.open

        def substituted_open(_path, flags):
            return real_open(outside, flags)

        monkeypatch.setattr(resolver_module.os, "open", substituted_open)
    with pytest.raises(AdmissionError, match="changed identity|escaped the configured store"):
        resolver_material["resolver"](reference, resolver_material["expected"], "gate-report")


def test_shared_resolver_keeps_concurrent_root_sessions_and_fake_ledger_isolated(
    resolver_material,
):
    _payload, _envelope, first = resolver_material["issue"](
        "gate-synthetic-001", "00000000000000000000000000000001"
    )
    _payload, _envelope, second = resolver_material["issue"](
        "gate-synthetic-002",
        "00000000000000000000000000000002",
        gate_id="before_pilot_readiness",
    )
    inputs = [first, second] * 8

    def resolve(reference):
        return resolver_material["resolver"](
            reference, resolver_material["expected"], "gate-report"
        ).artifact_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(resolve, inputs))
    assert results.count("gate-synthetic-001") == 8
    assert results.count("gate-synthetic-002") == 8
