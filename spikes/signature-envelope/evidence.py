from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


SPIKE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SPIKE_ROOT.parents[1]
EVIDENCE_PATH = SPIKE_ROOT / "evidence/signature-envelope.latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    versions = {
        name: importlib.metadata.version(name)
        for name in ("in-toto", "securesystemslib", "cryptography", "rfc8785", "psycopg")
    }
    return {
        "schema_version": 1,
        "task_id": "T-REVAL-019",
        "follow_on_task_ids": ["T-REVAL-020"],
        "decision_date": "2026-09-22",
        "data_mode": "synthetic-only",
        "decision": "accept-dsse-rfc8785-ed25519-for-development",
        "production_authorization": False,
        "removed_component": "CLASS-OS-SIGNATURE-V1 custom byte framing",
        "proven_components": [
            "one local verifier library",
            "one independently root/quorum-verified role-key registry snapshot",
            "table-driven artifact policy and trusted context binding",
            "verified nested-artifact result contract with type, digest, lifecycle and exact scope binding",
            "bounded rooted artifact-store fetch with strict envelope parse, payload digest and DSSE/policy verification",
            "recursive nested-reference cycle/depth/node limits and fail-closed identity-ledger port",
            "PostgreSQL database-enforced durable artifact-id and nonce uniqueness with concurrent/restart/outage evidence",
            "parent-signed generic ID/type/digest and catalog binding with DSSE-verified locator-only catalog closure",
            "Windows flat-root final-component CreateFileW no-follow and same-handle reparse/containment checks under protected-root assumption",
        ],
        "required_but_not_proven_here": [
            "protected production root-pin installation and rotation ceremony",
            "PostgreSQL transaction for setup consumption, allocation, ledger, audit and immutable receipt",
            "production artifact-root ACL, parent-namespace protection, rotation and deployment self-check",
        ],
        "not_runtime_components": [
            "online signing service",
            "online key registry service",
            "Sigstore transparency log dependency",
            "per-artifact approval microservice",
        ],
        "dependency_versions": versions,
        "licenses": {
            "in-toto": "Apache-2.0",
            "securesystemslib": "MIT",
            "cryptography": "Apache-2.0 OR BSD-3-Clause",
            "rfc8785": "Apache-2.0",
            "psycopg": "LGPL-3.0-only",
        },
        "official_sources": {
            "dsse": "https://github.com/secure-systems-lab/dsse/blob/master/protocol.md",
            "rfc8032": "https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1",
            "rfc8785": "https://www.rfc-editor.org/rfc/rfc8785.html",
            "github_attestations": "https://docs.github.com/en/actions/concepts/security/artifact-attestations",
        },
        "definition_hashes": {
            ".ai/gates/signed-artifact-policy.yaml": digest(
                REPO_ROOT / ".ai/gates/signed-artifact-policy.yaml"
            ),
            ".ai/gates/signature-canonicalization-test-vectors.yaml": digest(
                REPO_ROOT / ".ai/gates/signature-canonicalization-test-vectors.yaml"
            ),
            "spikes/signature-envelope/migrations/001_artifact_identity_ledger.sql": digest(
                SPIKE_ROOT / "migrations/001_artifact_identity_ledger.sql"
            ),
        },
        "coverage": {
            "official_vectors": ["DSSE PAE", "RFC 8032 Ed25519 test 1", "RFC 8785 sample and property ordering"],
            "negative_classes": [
                "payload/payloadType/signature mutation",
                "target commit and definition hash mutation",
                "duplicate key and NFC collision",
                "self reference",
                "missing role and duplicate principal",
                "wrong key usage and revoked key/artifact",
                "missing required signed field",
                "old/same-generation/broken-chain registry",
                "expiry",
                "wrong lifecycle and consumption",
                "one-time lifecycle fake idempotency and conflict (not transaction evidence)",
                "wrong root and missing registry quorum",
                "validly re-signed stale or foreign trusted context",
                "strict per-artifact required and unknown fields",
                "reference cycle and unresolved reference",
                "key status required and inactive key quorum denial",
                "scope setup operation/allocation and external reference-verifier fail-closed port",
                "nested admission receipt/report context binding",
                "receipt owner/class/term scope, reference type/digest and closed module-set mismatch",
                "referenced artifact policy-role quorum mismatch",
                "setup and admission shadow decisions require a verified go result",
                "shadow decision enum and receipt forbidden business content",
                "mutable state content-hash and verified transition binding",
                "concrete rooted URI scheme/authority/traversal/size/UTF-8/duplicate-envelope rejection",
                "fetched payload digest, DSSE signature, expected type and trusted-context mismatch",
                "recursive concrete-reference cycle, depth and node bounds",
                "artifact-id and nonce collision through an explicit non-durable test ledger",
                "candidate/pilot gate identity, distinctness and release-level versus workspace-level scope",
                "opened-handle identity and concurrent resolver-session isolation",
                "PostgreSQL concurrent idempotency, artifact-id/nonce conflicts, rollback, restart persistence and outage fail-closed",
                "generic closure direct-admission bypass, missing/tampered/swapped catalog, wrong target type/digest, revoked/expired catalog or target, and concurrent root sessions",
                "Windows real junction and final-component post-precheck junction replacement rejected by native handle reparse check",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "check"))
    args = parser.parse_args()
    generated = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.mode == "write":
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(generated, encoding="utf-8", newline="\n")
        print(EVIDENCE_PATH)
        return 0
    if not EVIDENCE_PATH.exists() or EVIDENCE_PATH.read_text(encoding="utf-8") != generated:
        raise SystemExit("signature-envelope evidence drift; run evidence.py write intentionally")
    print("signature-envelope evidence matches locked dependencies and definitions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
