"""T-REVAL-019: maintained DSSE primitives plus explicit Class OS policy.

The module is executable design evidence, not a production authorization
service. It never grants release authorization and it contains no production
key material.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Protocol

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from in_toto.models.metadata import Envelope
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import CryptoSigner, SSlibKey


REGISTRY_PAYLOAD_TYPE = "application/vnd.class-os.role-key-registry.v1+json"
ARTIFACT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ROOT_REGISTRY_ROLES = frozenset({"offline-root", "security", "operations"})
R1_ALLOWED_MODULES = frozenset({"roster", "fact-events", "tasks", "timeline-today", "exit-export"})
GATE_REPORT_REFERENCE_FIELDS = frozenset(
    {
        "artifact_id",
        "artifact_uri",
        "sha256",
        "gate_id",
        "gate_definition_sha256",
        "definition_bundle_sha256",
        "verifier_digest",
        "target_release_digest",
        "target_commit",
        "environment_digest",
    }
)
GATE_SLOT_IDS = {
    "candidate_gate_report": "before_release_candidate",
    "pilot_readiness_gate_report": "before_pilot_readiness",
}
KEY_STATUSES = frozenset({"active", "disabled", "retired", "compromised"})
KEY_FIELDS = frozenset(
    {
        "key_id",
        "signer_id",
        "role",
        "algorithm",
        "public_key",
        "key_usage",
        "not_before",
        "not_after",
        "status",
        "revoked_at",
    }
)
COMMON_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_type",
        "artifact_id",
        "lifecycle",
        "issued_at",
        "not_before",
        "expires_at",
        "nonce",
        "target_release_digest",
        "target_commit",
        "registry",
        "required_roles",
        "required_key_usage",
        "referenced_artifact_ids",
    }
)
GENERIC_REFERENCE_FIELDS = frozenset({"reference_bindings", "reference_catalog"})


@dataclass(frozen=True)
class ArtifactPolicy:
    payload_type: str
    lifecycle: str
    roles: frozenset[str]
    key_usage: str
    required_fields: frozenset[str]
    optional_fields: frozenset[str] = frozenset()


def _policy(
    artifact_type: str,
    lifecycle: str,
    roles: Iterable[str],
    key_usage: str,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> ArtifactPolicy:
    return ArtifactPolicy(
        payload_type=f"application/vnd.class-os.{artifact_type}.v1+json",
        lifecycle=lifecycle,
        roles=frozenset(roles),
        key_usage=key_usage,
        required_fields=frozenset(required),
        optional_fields=frozenset(optional),
    )


ARTIFACT_POLICIES: Mapping[str, ArtifactPolicy] = {
    "definition-bundle-approval": _policy(
        "definition-bundle-approval",
        "reusable-attestation",
        ("product", "privacy", "security", "engineering"),
        "definition-approval",
        ("definition_bundle_sha256",),
    ),
    "architecture-approval": _policy(
        "architecture-approval",
        "reusable-attestation",
        ("product", "security", "architecture", "operations"),
        "architecture-approval",
        (
            "definition_bundle_sha256",
            "approved_architecture_sha256",
            "approved_adr_sha256",
            "approved_spike_evidence",
            "constraints_sha256",
        ),
    ),
    "gate-report": _policy(
        "gate-report",
        "reusable-attestation",
        ("release-verifier",),
        "gate-report",
        (
            "artifact_uri",
            "sha256",
            "produced_at",
            "gate_id",
            "gate_definition_sha256",
            "definition_bundle_sha256",
            "verifier_digest",
            "environment_digest",
        ),
    ),
    "reference-catalog": _policy(
        "reference-catalog",
        "reusable-attestation",
        ("release-verifier",),
        "reference-catalog",
        ("entries",),
    ),
    "shadow-value-decision": _policy(
        "shadow-value-decision",
        "reusable-attestation",
        ("product", "pilot-owner", "release-verifier"),
        "shadow-value-decision",
        (
            "environment_digest",
            "workspace_id",
            "pilot_owner_id",
            "measurement_protocol_sha256",
            "result",
            "cost_summary_sha256",
            "evidence_index_sha256",
        ),
    ),
    "real-data-scope-setup": _policy(
        "real-data-scope-setup",
        "one-time-capability",
        ("product", "privacy", "security", "operations"),
        "scope-setup",
        (
            "definition_bundle_sha256",
            "environment_digest",
            "deployment_id",
            "owner_ids",
            "workspace_id",
            "candidate_gate_report",
            "pilot_readiness_gate_report",
            "shadow_value_decision",
            "allowed_operation",
            "maximum_allocations",
            "revocation_id",
        ),
    ),
    "scope-allocation-receipt": _policy(
        "scope-allocation-receipt",
        "reusable-attestation",
        ("deployment-runtime",),
        "scope-allocation-receipt",
        (
            "setup_artifact_id",
            "deployment_id",
            "owner_ids",
            "workspace_id",
            "reserved_class_ids",
            "reserved_term_ids",
            "environment_digest",
            "ledger_sequence",
            "ledger_entry_sha256",
            "allocated_at",
        ),
    ),
    "real-data-admission": _policy(
        "real-data-admission",
        "renewable-authorization",
        ("product", "privacy", "security", "operations"),
        "real-data-admission",
        (
            "definition_bundle_sha256",
            "environment_digest",
            "deployment_id",
            "owner_ids",
            "workspace_id",
            "class_ids",
            "term_ids",
            "scope_allocation_receipt",
            "allowed_modules",
            "evidence_references",
            "revocation_id",
        ),
    ),
    "state-transition": _policy(
        "state-transition",
        "reusable-attestation",
        ("release-verifier",),
        "state-transition",
        ("state_type", "state_sha256", "definition_bundle_sha256"),
    ),
}


class AdmissionError(ValueError):
    """Fail-closed validation error without an authorization side effect."""


@dataclass(frozen=True)
class ExpectedContext:
    artifact_type: str
    target_release_digest: str
    target_commit: str
    definition_bundle_sha256: str | None = None
    environment_digest: str | None = None
    deployment_id: str | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class VerifiedRegistrySnapshot:
    registry: dict[str, Any]
    sha256: str
    generation: int
    verified_roles: frozenset[str]
    expires_at: datetime


@dataclass(frozen=True)
class AdmissionDecision:
    artifact_id: str
    lifecycle: str
    cryptographic_valid: bool
    policy_valid: bool
    eligible: bool
    release_authorized: bool
    roles: frozenset[str]
    payload: dict[str, Any]


@dataclass(frozen=True)
class VerifiedArtifactReference:
    """Opaque result of concrete fetch/hash/DSSE verification at the adapter port."""

    artifact_id: str
    artifact_type: str
    lifecycle: str
    digest: str
    canonical_payload: bytes
    registry_generation: int
    registry_sha256: str
    verified_roles: frozenset[str]


@dataclass(frozen=True)
class VerifiedGenericClosure:
    parent_artifact_id: str
    parent_payload_sha256: str
    catalog_artifact_id: str
    catalog_payload_sha256: str
    registry_generation: int
    registry_sha256: str
    expected_context: ExpectedContext
    resolved: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class ConsumptionReceipt:
    artifact_id: str
    deployment_id: str
    workspace_id: str
    request_digest: str
    consumed_at: datetime


class LifecycleConsumptionFake:
    """Deterministic fake for lifecycle semantics, not transaction evidence."""

    def __init__(self) -> None:
        self._receipts: dict[tuple[str, str], ConsumptionReceipt] = {}

    def consume(
        self,
        decision: AdmissionDecision,
        deployment_id: str,
        workspace_id: str,
        request_digest: str,
        now: datetime,
    ) -> ConsumptionReceipt:
        if not decision.eligible or decision.lifecycle != "one-time-capability":
            raise AdmissionError("artifact is not an eligible one-time setup")
        key = (deployment_id, decision.artifact_id)
        prior = self._receipts.get(key)
        if prior is not None:
            if prior.workspace_id == workspace_id and prior.request_digest == request_digest:
                return prior
            raise AdmissionError("one-time setup conflicts with the existing consumption")
        receipt = ConsumptionReceipt(
            decision.artifact_id, deployment_id, workspace_id, request_digest, now
        )
        self._receipts[key] = receipt
        return receipt


def canonicalize_payload(value: Any) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise AdmissionError("payload is outside the RFC 8785/I-JSON profile") from exc


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dsse_pae(payload_type: str, payload: bytes) -> bytes:
    return Envelope(payload=payload, payload_type=payload_type, signatures={}).pae()


def sign_envelope(
    payload: dict[str, Any] | bytes,
    payload_type: str,
    signers: Iterable[tuple[str, Ed25519PrivateKey]],
    *,
    payload_is_bytes: bool = False,
) -> dict[str, Any]:
    payload_bytes = payload if payload_is_bytes else canonicalize_payload(payload)
    if not isinstance(payload_bytes, bytes):
        raise TypeError("payload must resolve to bytes")
    envelope = Envelope(payload=payload_bytes, payload_type=payload_type, signatures={})
    for key_id, private_key in signers:
        public_key = SSlibKey.from_crypto(private_key.public_key(), keyid=key_id)
        envelope.create_signature(CryptoSigner(private_key, public_key))
    return envelope.to_dict()


def verify_rfc8032_known_answer(
    *,
    secret_key_hex: str,
    public_key_hex: str,
    message: bytes,
    expected_signature_hex: str,
) -> bool:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(secret_key_hex))
    derived_public = private_key.public_key().public_bytes_raw().hex()
    if derived_public != public_key_hex:
        raise AdmissionError("RFC 8032 derived public key mismatch")
    signature = private_key.sign(message)
    if signature.hex() != expected_signature_hex:
        raise AdmissionError("RFC 8032 known-answer signature mismatch")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(signature, message)
    return True


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _strict_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                AdmissionError(f"non-I-JSON number: {item}")
            ),
        )
    except AdmissionError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdmissionError("payload is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AdmissionError("signed payload must be a JSON object")
    _reject_nfc_collisions(value)
    if canonicalize_payload(value) != payload:
        raise AdmissionError("payload bytes are not the RFC 8785 canonical representation")
    return value


def _reject_nfc_collisions(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        normalized: dict[str, str] = {}
        for key, nested in value.items():
            nfc = unicodedata.normalize("NFC", key)
            prior = normalized.get(nfc)
            if prior is not None and prior != key:
                raise AdmissionError(f"NFC collision at {path}: {prior!r} and {key!r}")
            normalized[nfc] = key
            _reject_nfc_collisions(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_nfc_collisions(nested, f"{path}[{index}]")


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AdmissionError(f"{field} must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AdmissionError(f"invalid {field}") from exc
    return parsed.astimezone(UTC)


def _key_records(records: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise AdmissionError(f"{label} keys must be a non-empty list")
    keys: dict[str, dict[str, Any]] = {}
    public_keys: set[str] = set()
    signer_ids: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise AdmissionError(f"{label} key record must be an object")
        if set(item) != KEY_FIELDS:
            raise AdmissionError(f"{label} key record fields are invalid")
        key_id = item.get("key_id")
        public_key = item.get("public_key")
        signer_id = item.get("signer_id")
        if not isinstance(key_id, str) or key_id in keys:
            raise AdmissionError(f"{label} key ids must be unique strings")
        if item.get("algorithm") != "Ed25519":
            raise AdmissionError(f"{label} algorithm is not allowed")
        if item.get("status") not in KEY_STATUSES:
            raise AdmissionError(f"{label} key status is invalid")
        if not isinstance(public_key, str) or public_key in public_keys:
            raise AdmissionError(f"{label} public keys must be unique")
        if not isinstance(signer_id, str) or signer_id in signer_ids:
            raise AdmissionError(f"{label} signer ids must be unique")
        keys[key_id] = item
        public_keys.add(public_key)
        signer_ids.add(signer_id)
    return keys


def _parse_envelope(envelope: dict[str, Any], payload_type: str) -> Envelope:
    try:
        parsed = Envelope.from_dict(copy.deepcopy(envelope))
    except (KeyError, TypeError, ValueError) as exc:
        raise AdmissionError("invalid DSSE envelope") from exc
    if parsed.payload_type != payload_type:
        raise AdmissionError("unexpected DSSE payload type")
    return parsed


def _verified_signers(
    envelope: Envelope, keys: Mapping[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    verified: dict[str, dict[str, Any]] = {}
    pae = envelope.pae()
    for key_id, signature in envelope.signatures.items():
        record = keys.get(key_id)
        if record is None:
            continue
        try:
            public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(record["public_key"]))
            SSlibKey.from_crypto(public, keyid=key_id).verify_signature(signature, pae)
        except (KeyError, TypeError, ValueError, UnverifiedSignatureError):
            continue
        verified[key_id] = record
    if not verified:
        raise AdmissionError("no trusted DSSE signature verified")
    return verified


def _valid_roles(
    verified: Mapping[str, dict[str, Any]], usage: str, signed_at: datetime
) -> frozenset[str]:
    roles: set[str] = set()
    for record in verified.values():
        if record.get("status") != "active":
            continue
        if record.get("key_usage") != usage:
            continue
        if signed_at < _timestamp(record.get("not_before"), "key.not_before"):
            continue
        if signed_at >= _timestamp(record.get("not_after"), "key.not_after"):
            continue
        revoked_at = record.get("revoked_at")
        if revoked_at is not None and signed_at >= _timestamp(revoked_at, "key.revoked_at"):
            continue
        role = record.get("role")
        if isinstance(role, str):
            roles.add(role)
    return frozenset(roles)


def _validate_registry_shape(registry: dict[str, Any]) -> tuple[str, int, datetime, dict[str, dict[str, Any]]]:
    required = {
        "schema_version",
        "generation",
        "previous_registry_sha256",
        "issued_at",
        "expires_at",
        "issued_artifacts",
        "revoked_artifacts",
        "keys",
    }
    if set(registry) != required or registry.get("schema_version") != 1:
        raise AdmissionError("registry schema fields/version are invalid")
    if not isinstance(registry.get("generation"), int) or registry["generation"] < 1:
        raise AdmissionError("registry generation is invalid")
    if not isinstance(registry.get("issued_artifacts"), list) or not isinstance(
        registry.get("revoked_artifacts"), list
    ):
        raise AdmissionError("registry artifact status lists are required")
    issued_at = _timestamp(registry.get("issued_at"), "registry.issued_at")
    expires_at = _timestamp(registry.get("expires_at"), "registry.expires_at")
    if issued_at >= expires_at:
        raise AdmissionError("registry validity window is invalid")
    raw = canonicalize_payload(registry)
    return sha256_hex(raw), registry["generation"], expires_at, _key_records(registry["keys"], "registry")


def verify_registry_envelope(
    envelope: dict[str, Any],
    trust_root: dict[str, Any],
    prior_pin: dict[str, Any],
    now: datetime,
) -> VerifiedRegistrySnapshot:
    """Activate a registry only after independent root/quorum verification."""

    if trust_root.get("schema_version") != 1:
        raise AdmissionError("unsupported trust-root schema")
    root_keys = _key_records(trust_root.get("keys"), "trust-root")
    parsed = _parse_envelope(envelope, REGISTRY_PAYLOAD_TYPE)
    verified = _verified_signers(parsed, root_keys)
    registry = _strict_json(parsed.payload)
    registry_hash, generation, expires_at, _ = _validate_registry_shape(registry)
    issued_at = _timestamp(registry["issued_at"], "registry.issued_at")
    root_roles = _valid_roles(verified, "registry-approval", issued_at)
    if not ROOT_REGISTRY_ROLES.issubset(root_roles):
        raise AdmissionError("registry root/security/operations quorum is not satisfied")
    if now < issued_at or now >= expires_at:
        raise AdmissionError("registry snapshot expired or is not active")

    minimum = prior_pin.get("minimum_generation")
    pinned_hash = prior_pin.get("registry_sha256")
    if not isinstance(minimum, int) or not isinstance(pinned_hash, str):
        raise AdmissionError("registry root pin is invalid")
    if generation < minimum:
        raise AdmissionError("registry generation is below the root pin")
    if generation == minimum and registry_hash != pinned_hash:
        raise AdmissionError("same-generation registry hash differs from root pin")
    if generation == minimum + 1 and registry.get("previous_registry_sha256") != pinned_hash:
        raise AdmissionError("previous registry hash does not match the root pin")
    if generation > minimum + 1:
        raise AdmissionError("registry generation chain is incomplete")
    return VerifiedRegistrySnapshot(
        registry=registry,
        sha256=registry_hash,
        generation=generation,
        verified_roles=root_roles,
        expires_at=expires_at,
    )


def _validate_hash(value: Any, field: str, *, prefix: bool = False) -> None:
    if not isinstance(value, str):
        raise AdmissionError(f"{field} must be a SHA-256 digest")
    candidate = value[7:] if prefix and value.startswith("sha256:") else value
    if prefix and not value.startswith("sha256:"):
        raise AdmissionError(f"{field} must use the sha256: prefix")
    if len(candidate) != 64 or candidate != candidate.lower():
        raise AdmissionError(f"{field} must be a SHA-256 digest")
    try:
        bytes.fromhex(candidate)
    except ValueError as exc:
        raise AdmissionError(f"{field} must be a SHA-256 digest") from exc


def _validate_context(payload: dict[str, Any], expected: ExpectedContext) -> None:
    bindings = {
        "artifact_type": expected.artifact_type,
        "target_release_digest": expected.target_release_digest,
        "target_commit": expected.target_commit,
        "definition_bundle_sha256": expected.definition_bundle_sha256,
        "environment_digest": expected.environment_digest,
        "deployment_id": expected.deployment_id,
        "workspace_id": expected.workspace_id,
    }
    for field, value in bindings.items():
        if value is not None and payload.get(field) != value:
            raise AdmissionError(f"trusted context mismatch: {field}")


class ReferenceVerifier(Protocol):
    """Trusted application port for typed artifacts and generic graph closure."""

    def __call__(
        self, reference: dict[str, Any], expected: ExpectedContext, artifact_type: str
    ) -> VerifiedArtifactReference: ...

    def resolve_generic_closure(
        self,
        parent_artifact_id: str,
        parent_payload_sha256: str,
        catalog_reference: dict[str, Any],
        bindings: tuple[dict[str, Any], ...],
        expected: ExpectedContext,
    ) -> VerifiedGenericClosure: ...


def _validate_reference(
    value: Any,
    expected: ExpectedContext,
    verifier: ReferenceVerifier | None,
    label: str,
    expected_type: str,
) -> dict[str, Any]:
    if verifier is None:
        raise AdmissionError(f"{label} requires the external reference-verifier port")
    if not isinstance(value, dict):
        raise AdmissionError(f"{label} reference verification failed")
    if expected_type == "gate-report" and set(value) != GATE_REPORT_REFERENCE_FIELDS:
        raise AdmissionError(f"{label} gate-report reference fields are invalid")
    verified = verifier(value, expected, expected_type)
    if not isinstance(verified, VerifiedArtifactReference):
        raise AdmissionError(f"{label} reference verifier returned an invalid result")
    if (
        verified.artifact_id != value.get("artifact_id")
        or verified.digest != value.get("sha256")
        or verified.artifact_type != expected_type
        or verified.registry_generation < 1
        or not verified.verified_roles
    ):
        raise AdmissionError(f"{label} verified reference metadata mismatch")
    _validate_hash(verified.digest, f"{label}.sha256")
    _validate_hash(verified.registry_sha256, f"{label}.registry_sha256")
    if sha256_hex(verified.canonical_payload) != verified.digest:
        raise AdmissionError(f"{label} verified payload digest mismatch")
    payload = _strict_json(verified.canonical_payload)
    policy = ARTIFACT_POLICIES.get(expected_type)
    if policy is None or verified.lifecycle != policy.lifecycle:
        raise AdmissionError(f"{label} verified reference lifecycle mismatch")
    if not policy.roles.issubset(verified.verified_roles):
        raise AdmissionError(f"{label} verified reference role quorum mismatch")
    if (
        payload.get("artifact_id") != verified.artifact_id
        or payload.get("artifact_type") != expected_type
        or payload.get("lifecycle") != verified.lifecycle
    ):
        raise AdmissionError(f"{label} verified payload identity mismatch")
    if expected_type == "gate-report":
        expected_gate_id = GATE_SLOT_IDS.get(label)
        if expected_gate_id is None or payload.get("gate_id") != expected_gate_id:
            raise AdmissionError(f"{label} gate_id binding mismatch")
        for field in (
            "gate_id",
            "gate_definition_sha256",
            "definition_bundle_sha256",
            "verifier_digest",
            "target_release_digest",
            "target_commit",
            "environment_digest",
        ):
            if value.get(field) != payload.get(field):
                raise AdmissionError(f"{label} verified gate reference binding mismatch: {field}")
    return payload


def _same(value: Mapping[str, Any], field: str, expected: Any, label: str) -> None:
    if value.get(field) != expected:
        raise AdmissionError(f"{label} binding mismatch: {field}")


def _unique_string_list(value: Any, label: str, *, non_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (non_empty and not value):
        raise AdmissionError(f"{label} must be a {'non-empty ' if non_empty else ''}string list")
    if any(not isinstance(item, str) or not item for item in value) or len(set(value)) != len(value):
        raise AdmissionError(f"{label} must contain unique non-empty strings")
    return tuple(value)


def _validate_additional_constraints(
    payload: dict[str, Any],
    expected: ExpectedContext,
    reference_verifier: ReferenceVerifier | None,
) -> None:
    artifact_type = payload["artifact_type"]
    if artifact_type == "reference-catalog":
        entries = payload["entries"]
        if not isinstance(entries, list) or len(entries) > 64:
            raise AdmissionError("reference catalog entries are invalid")
        if payload["referenced_artifact_ids"]:
            raise AdmissionError("reference catalog cannot contain generic references")
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "artifact_id", "artifact_uri"
            }:
                raise AdmissionError("reference catalog entry fields are invalid")
            artifact_id = entry["artifact_id"]
            if (
                not isinstance(artifact_id, str)
                or not ARTIFACT_ID_PATTERN.fullmatch(artifact_id)
                or artifact_id in seen
                or artifact_id == payload["artifact_id"]
            ):
                raise AdmissionError("reference catalog artifact ids are invalid")
            if not isinstance(entry["artifact_uri"], str) or not entry["artifact_uri"]:
                raise AdmissionError("reference catalog artifact URI is invalid")
            seen.add(artifact_id)
    if artifact_type == "shadow-value-decision" and payload["result"] not in {
        "go",
        "change",
        "stop",
    }:
        raise AdmissionError("shadow-value result is invalid")
    if artifact_type == "real-data-scope-setup":
        _unique_string_list(payload["owner_ids"], "owner_ids")
        if payload["allowed_operation"] != "allocate-workspace-bound-empty-scope-only":
            raise AdmissionError("scope setup operation is invalid")
        if payload["maximum_allocations"] != 1:
            raise AdmissionError("scope setup maximum_allocations must equal one")
        expected_types = {
            "candidate_gate_report": "gate-report",
            "pilot_readiness_gate_report": "gate-report",
            "shadow_value_decision": "shadow-value-decision",
        }
        verified_gate_references: dict[str, tuple[str, str]] = {}
        for field, expected_type in expected_types.items():
            reference = payload[field]
            verified_payload = _validate_reference(
                reference, expected, reference_verifier, field, expected_type
            )
            bindings = [
                ("target_release_digest", expected.target_release_digest),
                ("target_commit", expected.target_commit),
                ("environment_digest", expected.environment_digest),
            ]
            if expected_type != "gate-report":
                bindings.append(("workspace_id", expected.workspace_id))
            for binding, binding_value in bindings:
                if binding_value is not None:
                    _same(verified_payload, binding, binding_value, field)
            if expected_type == "gate-report":
                verified_gate_references[field] = (reference["artifact_id"], reference["sha256"])
            if expected_type == "shadow-value-decision" and verified_payload.get("result") != "go":
                raise AdmissionError("scope setup requires a verified shadow go decision")
        if len(set(verified_gate_references.values())) != len(verified_gate_references):
            raise AdmissionError("candidate and pilot gate reports must be distinct")
    if artifact_type == "scope-allocation-receipt":
        forbidden = {"student", "person_name", "record", "task", "class_business_state", "term_business_state"}
        def contains_forbidden(value: Any) -> bool:
            if isinstance(value, dict):
                return bool(forbidden.intersection(value)) or any(
                    contains_forbidden(nested) for nested in value.values()
                )
            if isinstance(value, list):
                return any(contains_forbidden(nested) for nested in value)
            return False

        if contains_forbidden(payload):
            raise AdmissionError("scope allocation receipt contains forbidden business fields")
    if artifact_type == "real-data-admission":
        owner_ids = _unique_string_list(payload["owner_ids"], "owner_ids")
        class_ids = _unique_string_list(payload["class_ids"], "class_ids")
        term_ids = _unique_string_list(payload["term_ids"], "term_ids")
        modules = frozenset(_unique_string_list(payload["allowed_modules"], "allowed_modules"))
        if not modules.issubset(R1_ALLOWED_MODULES):
            raise AdmissionError("real-data admission contains an unknown module")
        receipt = payload["scope_allocation_receipt"]
        receipt_payload = _validate_reference(
            receipt,
            expected,
            reference_verifier,
            "scope_allocation_receipt",
            "scope-allocation-receipt",
        )
        for field, value in (
            ("target_release_digest", expected.target_release_digest),
            ("target_commit", expected.target_commit),
            ("environment_digest", expected.environment_digest),
            ("deployment_id", expected.deployment_id),
            ("workspace_id", expected.workspace_id),
        ):
            if value is not None:
                _same(receipt_payload, field, value, "scope_allocation_receipt")
        for field, value in (
            ("owner_ids", owner_ids),
            ("reserved_class_ids", class_ids),
            ("reserved_term_ids", term_ids),
        ):
            receipt_values = _unique_string_list(
                receipt_payload.get(field), f"scope_allocation_receipt.{field}"
            )
            if frozenset(receipt_values) != frozenset(value):
                raise AdmissionError(f"scope_allocation_receipt binding mismatch: {field}")
        references = payload["evidence_references"]
        expected_types = {
            "candidate_gate_report": "gate-report",
            "pilot_readiness_gate_report": "gate-report",
            "shadow_value_decision": "shadow-value-decision",
        }
        if not isinstance(references, dict) or set(references) != set(expected_types):
            raise AdmissionError("real-data admission evidence references are required")
        verified_gate_references: dict[str, tuple[str, str]] = {}
        for name, reference in references.items():
            verified_payload = _validate_reference(
                reference, expected, reference_verifier, name, expected_types[name]
            )
            bindings = [
                ("target_release_digest", expected.target_release_digest),
                ("target_commit", expected.target_commit),
                ("environment_digest", expected.environment_digest),
            ]
            if expected_types[name] != "gate-report":
                bindings.append(("workspace_id", expected.workspace_id))
            for field, value in bindings:
                if value is not None:
                    _same(verified_payload, field, value, name)
            if expected_types[name] == "gate-report":
                verified_gate_references[name] = (reference["artifact_id"], reference["sha256"])
            if expected_types[name] == "shadow-value-decision" and verified_payload.get("result") != "go":
                raise AdmissionError("real-data admission requires a verified shadow go decision")
        if len(set(verified_gate_references.values())) != len(verified_gate_references):
            raise AdmissionError("candidate and pilot gate reports must be distinct")


def verify_admission(
    envelope: dict[str, Any],
    registry_snapshot: VerifiedRegistrySnapshot,
    now: datetime,
    expected: ExpectedContext,
    reference_verifier: ReferenceVerifier | None = None,
) -> AdmissionDecision:
    if not isinstance(registry_snapshot, VerifiedRegistrySnapshot):
        raise AdmissionError("admission requires a root-verified registry snapshot")
    policy = ARTIFACT_POLICIES.get(expected.artifact_type)
    if policy is None:
        raise AdmissionError("unsupported expected artifact type")
    parsed = _parse_envelope(envelope, policy.payload_type)
    key_records = _key_records(registry_snapshot.registry["keys"], "registry")
    verified = _verified_signers(parsed, key_records)
    payload = _strict_json(parsed.payload)

    allowed = COMMON_FIELDS | GENERIC_REFERENCE_FIELDS | policy.required_fields | policy.optional_fields | {"consumption"}
    missing = sorted((COMMON_FIELDS | policy.required_fields) - payload.keys())
    unknown = sorted(payload.keys() - allowed)
    if missing:
        raise AdmissionError(f"signed payload missing required fields: {missing}")
    if unknown:
        raise AdmissionError(f"signed payload contains unknown fields: {unknown}")
    if payload.get("schema_version") != 1:
        raise AdmissionError("unsupported signed payload schema version")
    if payload.get("artifact_type") != expected.artifact_type:
        raise AdmissionError("trusted context mismatch: artifact_type")
    if payload.get("lifecycle") != policy.lifecycle:
        raise AdmissionError("artifact lifecycle does not match policy")
    if frozenset(payload.get("required_roles", [])) != policy.roles:
        raise AdmissionError("payload role policy differs from verifier policy")
    if payload.get("required_key_usage") != policy.key_usage:
        raise AdmissionError("payload key usage differs from verifier policy")

    binding = payload.get("registry")
    if not isinstance(binding, dict) or set(binding) != {"generation", "sha256"}:
        raise AdmissionError("payload registry binding is invalid")
    if binding["generation"] != registry_snapshot.generation or binding["sha256"] != registry_snapshot.sha256:
        raise AdmissionError("payload registry binding mismatch")
    if now >= registry_snapshot.expires_at:
        raise AdmissionError("verified registry snapshot expired")

    _validate_context(payload, expected)
    _validate_additional_constraints(payload, expected, reference_verifier)
    _validate_hash(payload["target_release_digest"], "target_release_digest", prefix=True)
    if not isinstance(payload["target_commit"], str) or len(payload["target_commit"]) != 40:
        raise AdmissionError("target commit must be a full object id")
    try:
        bytes.fromhex(payload["target_commit"])
    except ValueError as exc:
        raise AdmissionError("target commit must be a full lowercase hexadecimal object id") from exc
    if payload["target_commit"] != payload["target_commit"].lower():
        raise AdmissionError("target commit must be a full lowercase hexadecimal object id")
    if "definition_bundle_sha256" in payload:
        _validate_hash(payload["definition_bundle_sha256"], "definition_bundle_sha256")
    if "environment_digest" in payload:
        _validate_hash(payload["environment_digest"], "environment_digest", prefix=True)
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or len(nonce) != 32 or nonce != nonce.lower():
        raise AdmissionError("nonce must be a 128-bit lowercase hex string")
    try:
        bytes.fromhex(nonce)
    except ValueError as exc:
        raise AdmissionError("nonce must be a 128-bit lowercase hex string") from exc

    artifact_id = payload.get("artifact_id")
    refs = payload.get("referenced_artifact_ids")
    if (
        not isinstance(artifact_id, str)
        or not ARTIFACT_ID_PATTERN.fullmatch(artifact_id)
        or not isinstance(refs, list)
        or len(refs) > 64
        or any(not isinstance(ref, str) or not ARTIFACT_ID_PATTERN.fullmatch(ref) for ref in refs)
        or len(refs) != len(set(refs))
    ):
        raise AdmissionError("artifact id and references are invalid")
    if artifact_id in refs:
        raise AdmissionError("artifact self-reference is forbidden")
    if refs:
        bindings = payload.get("reference_bindings")
        catalog = payload.get("reference_catalog")
        if not isinstance(bindings, list) or len(bindings) != len(refs):
            raise AdmissionError("generic reference bindings are required")
        if not isinstance(catalog, dict) or set(catalog) != {"artifact_id", "artifact_uri", "sha256"}:
            raise AdmissionError("signed reference catalog binding is required")
        if not isinstance(catalog["artifact_id"], str) or not ARTIFACT_ID_PATTERN.fullmatch(catalog["artifact_id"]):
            raise AdmissionError("signed reference catalog id is invalid")
        if not isinstance(catalog["artifact_uri"], str) or not catalog["artifact_uri"]:
            raise AdmissionError("signed reference catalog URI is invalid")
        if not isinstance(catalog["sha256"], str) or not SHA256_PATTERN.fullmatch(catalog["sha256"]):
            raise AdmissionError("signed reference catalog digest is invalid")
        for reference_id, binding_item in zip(refs, bindings, strict=True):
            if not isinstance(binding_item, dict) or set(binding_item) != {"artifact_id", "artifact_type", "sha256"}:
                raise AdmissionError("generic reference binding fields are invalid")
            if binding_item["artifact_id"] != reference_id:
                raise AdmissionError("generic reference binding id mismatch")
            if (
                not isinstance(binding_item["artifact_type"], str)
                or binding_item["artifact_type"] not in ARTIFACT_POLICIES
                or binding_item["artifact_type"] == "reference-catalog"
            ):
                raise AdmissionError("generic reference binding type is invalid")
            if not isinstance(binding_item["sha256"], str) or not SHA256_PATTERN.fullmatch(binding_item["sha256"]):
                raise AdmissionError("generic reference binding digest is invalid")
    elif GENERIC_REFERENCE_FIELDS.intersection(payload):
        raise AdmissionError("unneeded generic reference bindings are forbidden")

    issued_at = _timestamp(payload.get("issued_at"), "issued_at")
    not_before = _timestamp(payload.get("not_before"), "not_before")
    expires_at = _timestamp(payload.get("expires_at"), "expires_at")
    if now < not_before:
        raise AdmissionError("artifact is not active yet")
    if now >= expires_at:
        raise AdmissionError("artifact expired")
    if issued_at > now or issued_at < not_before or issued_at >= expires_at:
        raise AdmissionError("artifact issuance time is invalid")

    registry = registry_snapshot.registry
    if artifact_id not in registry["issued_artifacts"]:
        raise AdmissionError("artifact is not issued by the active registry")
    if artifact_id in registry["revoked_artifacts"]:
        raise AdmissionError("artifact is revoked by the active registry")
    roles = _valid_roles(verified, policy.key_usage, issued_at)
    if not policy.roles.issubset(roles):
        raise AdmissionError("role quorum is not satisfied")

    consumption = payload.get("consumption")
    if policy.lifecycle in {"reusable-attestation", "renewable-authorization"} and consumption is not None:
        raise AdmissionError(f"{policy.lifecycle} must not be consumed")
    if refs:
        resolver = getattr(reference_verifier, "resolve_generic_closure", None)
        if not callable(resolver):
            raise AdmissionError("generic references require a closure verifier")
        parent_digest = sha256_hex(parsed.payload)
        closure = resolver(
            artifact_id, parent_digest, catalog, tuple(bindings), expected
        )
        if not isinstance(closure, VerifiedGenericClosure) or (
            closure.parent_artifact_id != artifact_id
            or closure.parent_payload_sha256 != parent_digest
            or closure.catalog_artifact_id != catalog["artifact_id"]
            or closure.catalog_payload_sha256 != catalog["sha256"]
            or closure.registry_generation != registry_snapshot.generation
            or closure.registry_sha256 != registry_snapshot.sha256
            or closure.expected_context != expected
            or closure.resolved != tuple(
                (item["artifact_id"], item["artifact_type"], item["sha256"])
                for item in bindings
            )
        ):
            raise AdmissionError("generic reference closure result does not match signed parent")
    return AdmissionDecision(
        artifact_id=artifact_id,
        lifecycle=policy.lifecycle,
        cryptographic_valid=True,
        policy_valid=True,
        eligible=True,
        release_authorized=False,
        roles=roles,
        payload=payload,
    )


def validate_reference_graph(payloads: Iterable[dict[str, Any]]) -> None:
    """Reject missing references and cycles across definition/state/evidence artifacts."""

    materialized = list(payloads)
    by_id = {item.get("artifact_id"): item for item in materialized}
    if None in by_id or len(by_id) != len(materialized):
        raise AdmissionError("artifact ids must be present and unique")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(artifact_id: str) -> None:
        if artifact_id in visiting:
            raise AdmissionError("artifact reference cycle is forbidden")
        if artifact_id in visited:
            return
        visiting.add(artifact_id)
        for reference in by_id[artifact_id].get("referenced_artifact_ids", []):
            if reference not in by_id:
                raise AdmissionError("unresolved artifact reference")
            walk(reference)
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    for artifact_id in by_id:
        walk(artifact_id)


def verify_mutable_state_binding(
    state: dict[str, Any],
    transition: AdmissionDecision,
    expected: ExpectedContext,
) -> str:
    """Verify external state-transition content binding without inline signatures."""

    if transition.payload.get("artifact_type") != "state-transition":
        raise AdmissionError("mutable state requires a verified state-transition artifact")
    if "state_transition_artifact" not in state:
        raise AdmissionError("mutable state transition reference is required")
    unsigned_state = {key: value for key, value in state.items() if key != "state_transition_artifact"}
    state_hash = sha256_hex(canonicalize_payload(unsigned_state))
    if transition.payload.get("state_sha256") != state_hash:
        raise AdmissionError("mutable state hash mismatch")
    _validate_context(transition.payload, expected)
    reference = state["state_transition_artifact"]
    if not isinstance(reference, dict) or reference.get("artifact_id") != transition.artifact_id:
        raise AdmissionError("mutable state transition reference mismatch")
    return state_hash
