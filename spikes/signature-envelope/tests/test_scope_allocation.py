"""Synthetic E-ADM-007/008/009 transaction contract; never real-data authorization."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from scope_allocation import ScopeAllocationCommand, ScopeAllocationStore, TrustedAllocationContext
from scope_allocation_schema import validate as validate_schema_contract
from signature_envelope import AdmissionError, VerifiedArtifactReference, VerifiedRegistrySnapshot


NOW = datetime(2029, 6, 1, tzinfo=UTC)
ROOT_DIGEST = "a" * 64
SETUP_DIGEST = "b" * 64


def verified_setup(
    *,
    artifact_id: str = "setup-synthetic-001",
    deployment_id: str = "deployment-synthetic-001",
    workspace_id: str = "workspace-synthetic-001",
) -> VerifiedArtifactReference:
    from signature_envelope import canonicalize_payload, sha256_hex

    payload = {
        "artifact_id": artifact_id,
        "deployment_id": deployment_id,
        "workspace_id": workspace_id,
        "owner_ids": ["owner-synthetic-001"],
        "environment_digest": "sha256:" + "c" * 64,
        "allowed_operation": "allocate-workspace-bound-empty-scope-only",
        "maximum_allocations": 1,
        "expires_at": "2029-06-30T00:00:00Z",
    }
    raw = canonicalize_payload(payload)
    return VerifiedArtifactReference(
        artifact_id=artifact_id,
        artifact_type="real-data-scope-setup",
        lifecycle="one-time-capability",
        digest=sha256_hex(raw),
        canonical_payload=raw,
        registry_generation=1,
        registry_sha256=ROOT_DIGEST,
        verified_roles=frozenset({"product", "privacy", "security", "operations"}),
    )


def active_registry() -> VerifiedRegistrySnapshot:
    return VerifiedRegistrySnapshot(
        registry={},
        sha256=ROOT_DIGEST,
        generation=1,
        verified_roles=frozenset({"offline-root", "security", "operations"}),
        expires_at=NOW + timedelta(days=10),
    )


def command(**changes: object) -> ScopeAllocationCommand:
    raw: dict[str, object] = {
        "command_type": "ScopeAllocationCommand",
        "deployment_id": "deployment-synthetic-001",
        "workspace_id": "workspace-synthetic-001",
        "setup_artifact_id": "setup-synthetic-001",
    }
    raw.update(changes)
    return ScopeAllocationCommand.parse(raw)


def trusted_context(request: ScopeAllocationCommand | None = None, *, actor: str = "owner-synthetic-001") -> TrustedAllocationContext:
    request = request or command()
    return TrustedAllocationContext(
        authenticated_actor_id=actor,
        session_id="session-synthetic-001",
        command_id="command-synthetic-001",
        reason="synthetic scope allocation drill",
        deployment_id=request.deployment_id,
        workspace_id=request.workspace_id,
    )


def live_store() -> ScopeAllocationStore:
    conninfo = os.environ.get("CLASS_OS_SCOPE_ALLOCATION_TEST_PG_DSN")
    admin_conninfo = os.environ.get("CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN")
    if not conninfo or not admin_conninfo:
        pytest.skip("isolated live PostgreSQL drill supplies the connection")
    store = ScopeAllocationStore(conninfo)
    store.migrate(admin_conninfo)
    return store


def test_command_is_exact_and_has_no_business_payload() -> None:
    assert command().setup_artifact_id == "setup-synthetic-001"
    for changes in (
        {"command_type": "CreateStudent"},
        {"student": {"name": "synthetic"}},
        {"reserved_class_id": "caller-chosen"},
        {"workspace_id": ""},
    ):
        with pytest.raises(AdmissionError):
            command(**changes)


def test_direct_command_construction_and_tampered_verified_payload_fail_closed() -> None:
    forged = ScopeAllocationCommand(
        "CreateStudent", "deployment-synthetic-001", "workspace-synthetic-001", "setup-synthetic-001"
    )
    with pytest.raises(AdmissionError):
        ScopeAllocationStore._verified_inputs(forged, verified_setup(), active_registry(), NOW, trusted_context())

    from dataclasses import replace

    setup = verified_setup()
    with pytest.raises(AdmissionError):
        ScopeAllocationStore._verified_inputs(
            command(), replace(setup, canonical_payload=b"{}"), active_registry(), NOW, trusted_context()
        )


def test_verified_setup_scope_expiry_and_registry_are_required() -> None:
    from dataclasses import replace

    for request, setup, registry, instant in (
        (command(workspace_id="workspace-other"), verified_setup(), active_registry(), NOW),
        (command(deployment_id="deployment-other"), verified_setup(), active_registry(), NOW),
        (command(), verified_setup(), replace(active_registry(), generation=2), NOW),
        (command(), verified_setup(), active_registry(), NOW + timedelta(days=31)),
    ):
        with pytest.raises(AdmissionError):
            ScopeAllocationStore._verified_inputs(request, setup, registry, instant, trusted_context(request))

    with pytest.raises(AdmissionError, match="owner context"):
        ScopeAllocationStore._verified_inputs(
            command(), verified_setup(), active_registry(), NOW,
            trusted_context(actor="not-an-owner"),
        )


def test_one_transaction_idempotence_and_conflicting_replay() -> None:
    store = live_store()
    first = store.allocate(command(), verified_setup(), active_registry(), NOW, trusted_context())
    repeated = store.allocate(command(), verified_setup(), active_registry(), NOW, trusted_context())
    assert repeated == first
    assert first["reserved_class_ids"] and first["reserved_term_ids"]
    assert store.counts("deployment-synthetic-001", "setup-synthetic-001") == (1, 1, 1, 1, 1)
    with pytest.raises(AdmissionError, match="conflict"):
        store.allocate(
            command(workspace_id="workspace-synthetic-002"),
            verified_setup(workspace_id="workspace-synthetic-002"),
            active_registry(),
            NOW,
            trusted_context(command(workspace_id="workspace-synthetic-002")),
        )
    assert store.counts("deployment-synthetic-001", "setup-synthetic-001") == (1, 1, 1, 1, 1)


@pytest.mark.parametrize(
    "fault_after", ["consumption", "allocation", "ledger", "audit", "receipt"]
)
def test_every_precommit_fault_rolls_back_all_five_members(fault_after: str) -> None:
    store = live_store()
    setup_id = f"setup-fault-{fault_after}"
    setup = verified_setup(artifact_id=setup_id, workspace_id=f"workspace-fault-{fault_after}")
    request = command(setup_artifact_id=setup_id, workspace_id=f"workspace-fault-{fault_after}")
    with pytest.raises(RuntimeError, match="injected precommit failure"):
        store.allocate(request, setup, active_registry(), NOW, trusted_context(request), fault_after=fault_after)
    assert store.counts("deployment-synthetic-001", setup_id) == (0, 0, 0, 0, 0)
    receipt = store.allocate(request, setup, active_registry(), NOW, trusted_context(request))
    assert receipt["setup_artifact_id"] == setup_id
    assert store.counts("deployment-synthetic-001", setup_id) == (1, 1, 1, 1, 1)


def test_concurrent_identical_setup_allocates_once() -> None:
    store = live_store()
    setup = verified_setup(artifact_id="setup-concurrent-001", workspace_id="workspace-concurrent-001")
    request = command(setup_artifact_id=setup.artifact_id, workspace_id="workspace-concurrent-001")

    def attempt(_index: int) -> dict:
        return store.allocate(request, setup, active_registry(), NOW, trusted_context(request))

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))
    assert all(outcome == outcomes[0] for outcome in outcomes)
    assert store.counts("deployment-synthetic-001", setup.artifact_id) == (1, 1, 1, 1, 1)


def test_same_workspace_cannot_be_allocated_by_a_second_setup() -> None:
    store = live_store()
    first = verified_setup(artifact_id="setup-workspace-a", workspace_id="workspace-unique-001")
    second = verified_setup(artifact_id="setup-workspace-b", workspace_id="workspace-unique-001")
    store.allocate(command(setup_artifact_id=first.artifact_id, workspace_id="workspace-unique-001"),
                   first, active_registry(), NOW, trusted_context(command(workspace_id="workspace-unique-001")))
    with pytest.raises(AdmissionError):
        store.allocate(command(setup_artifact_id=second.artifact_id, workspace_id="workspace-unique-001"),
                       second, active_registry(), NOW, trusted_context(command(workspace_id="workspace-unique-001")))
    assert store.counts("deployment-synthetic-001", first.artifact_id) == (1, 1, 1, 1, 1)
    assert store.counts("deployment-synthetic-001", second.artifact_id) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "mutation",
    [
        "ALTER TABLE class_os_gate.scope_allocation "
        "DROP CONSTRAINT scope_allocation_deployment_id_workspace_id_key",
        "ALTER TABLE class_os_gate.scope_allocation "
        "DROP CONSTRAINT scope_allocation_deployment_id_setup_artifact_id_fkey",
        "ALTER TABLE class_os_gate.scope_allocation_audit "
        "DROP CONSTRAINT scope_allocation_audit_event_type_check",
        "ALTER TABLE class_os_gate.scope_receipt_payload "
        "DISABLE TRIGGER scope_receipt_payload_immutable",
        "ALTER TABLE class_os_gate.scope_allocation SET UNLOGGED",
    ],
)
def test_hostile_schema_mutation_fails_exact_contract(mutation: str) -> None:
    store = live_store()
    with psycopg.connect(os.environ["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"]) as connection:
        connection.execute(mutation)
        with pytest.raises(AdmissionError, match="schema contract mismatch"):
            validate_schema_contract(connection)
        connection.rollback()


def test_postcommit_signer_failure_only_retries_original_receipt() -> None:
    store = live_store()
    setup = verified_setup(artifact_id="setup-signer-001", workspace_id="workspace-signer-001")
    request = command(setup_artifact_id=setup.artifact_id, workspace_id="workspace-signer-001")
    with pytest.raises(RuntimeError, match="signer unavailable"):
        store.allocate_and_deliver(
            request, setup, active_registry(), NOW, trusted_context(request),
            deliver=lambda _payload: (_ for _ in ()).throw(RuntimeError("signer unavailable")),
        )
    first = store.allocate(request, setup, active_registry(), NOW, trusted_context(request))
    assert store.allocate_and_deliver(
        request, setup, active_registry(), NOW, trusted_context(request), deliver=lambda payload: payload,
    ) == first
    assert store.counts("deployment-synthetic-001", setup.artifact_id) == (1, 1, 1, 1, 1)


def test_tampered_audit_row_makes_retry_fail_closed() -> None:
    store = live_store()
    setup = verified_setup(artifact_id="setup-tamper-001", workspace_id="workspace-tamper-001")
    request = command(setup_artifact_id=setup.artifact_id, workspace_id="workspace-tamper-001")
    context = trusted_context(request)
    original = store.allocate(request, setup, active_registry(), NOW, context)
    admin_dsn = os.environ["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"]
    with psycopg.connect(admin_dsn) as connection:
        previous = connection.execute(
            "SELECT request_sha256 FROM class_os_gate.scope_allocation_audit "
            "WHERE deployment_id = %s AND setup_artifact_id = %s",
            (request.deployment_id, request.setup_artifact_id),
        ).fetchone()[0]
        connection.execute("ALTER TABLE class_os_gate.scope_allocation_audit "
                           "DISABLE TRIGGER scope_allocation_audit_immutable")
        connection.execute(
            "UPDATE class_os_gate.scope_allocation_audit SET request_sha256 = %s "
            "WHERE deployment_id = %s AND setup_artifact_id = %s",
            ("0" * 64, request.deployment_id, request.setup_artifact_id),
        )
        connection.execute("ALTER TABLE class_os_gate.scope_allocation_audit "
                           "ENABLE TRIGGER scope_allocation_audit_immutable")
    try:
        with pytest.raises(AdmissionError, match="evidence mismatch"):
            store.allocate(request, setup, active_registry(), NOW, context)
    finally:
        with psycopg.connect(admin_dsn) as connection:
            connection.execute("ALTER TABLE class_os_gate.scope_allocation_audit "
                               "DISABLE TRIGGER scope_allocation_audit_immutable")
            connection.execute(
                "UPDATE class_os_gate.scope_allocation_audit SET request_sha256 = %s "
                "WHERE deployment_id = %s AND setup_artifact_id = %s",
                (previous, request.deployment_id, request.setup_artifact_id),
            )
            connection.execute("ALTER TABLE class_os_gate.scope_allocation_audit "
                               "ENABLE TRIGGER scope_allocation_audit_immutable")
    assert store.allocate(request, setup, active_registry(), NOW, context) == original


@pytest.mark.parametrize(
    "table",
    [
        "scope_setup_consumption", "scope_allocation", "scope_allocation_ledger",
        "scope_allocation_audit", "scope_receipt_payload",
    ],
)
def test_transaction_rows_are_database_immutable(table: str) -> None:
    store = live_store()
    setup_id = f"setup-immutable-{table}"
    setup = verified_setup(artifact_id=setup_id, workspace_id=f"workspace-immutable-{table}")
    request = command(setup_artifact_id=setup.artifact_id, workspace_id=f"workspace-immutable-{table}")
    store.allocate(request, setup, active_registry(), NOW, trusted_context(request))
    with psycopg.connect(os.environ["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"]) as connection:
        with pytest.raises(psycopg.Error):
            connection.execute(
                f"UPDATE class_os_gate.{table} SET deployment_id = deployment_id "
                "WHERE deployment_id = %s AND setup_artifact_id = %s",
                (request.deployment_id, setup.artifact_id),
            )


def test_runtime_writer_has_no_mutation_or_schema_authority() -> None:
    store = live_store()
    with psycopg.connect(store.conninfo) as connection:
        ScopeAllocationStore._validate_runtime_role(connection)
        with pytest.raises(psycopg.Error):
            connection.execute("TRUNCATE class_os_gate.scope_receipt_payload")

    admin = ScopeAllocationStore(os.environ["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"])
    with pytest.raises(AdmissionError, match="restricted runtime writer"):
        admin.allocate(
            command(setup_artifact_id="setup-admin-forbidden", workspace_id="workspace-admin-forbidden"),
            verified_setup(artifact_id="setup-admin-forbidden", workspace_id="workspace-admin-forbidden"),
            active_registry(), NOW,
            trusted_context(command(workspace_id="workspace-admin-forbidden")),
        )
    assert store.counts("deployment-synthetic-001", "setup-admin-forbidden") == (0, 0, 0, 0, 0)


@pytest.mark.parametrize("extra_grant", [
    "GRANT TRIGGER ON class_os_gate.scope_allocation TO class_os_scope_writer",
    "GRANT REFERENCES ON class_os_gate.scope_allocation TO class_os_scope_writer",
    "GRANT SELECT ON SEQUENCE class_os_gate.scope_allocation_ledger_sequence TO class_os_scope_writer",
])
def test_runtime_writer_rejects_extra_grants(extra_grant: str) -> None:
    store = live_store()
    admin_dsn = os.environ["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"]
    with psycopg.connect(admin_dsn) as connection:
        connection.execute(extra_grant)
    try:
        with psycopg.connect(store.conninfo) as connection:
            with pytest.raises(AdmissionError, match="privilege mismatch"):
                ScopeAllocationStore._validate_runtime_role(connection)
    finally:
        with psycopg.connect(admin_dsn) as connection:
            if "SEQUENCE" in extra_grant:
                connection.execute(
                    "REVOKE SELECT ON SEQUENCE class_os_gate.scope_allocation_ledger_sequence "
                    "FROM class_os_scope_writer"
                )
            else:
                privilege = "TRIGGER" if "TRIGGER" in extra_grant else "REFERENCES"
                connection.execute(
                    f"REVOKE {privilege} ON class_os_gate.scope_allocation FROM class_os_scope_writer"
                )


def test_truncate_trigger_rejects_even_admin_role() -> None:
    live_store()
    with psycopg.connect(os.environ["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"]) as connection:
        with pytest.raises(psycopg.Error, match="immutable"):
            connection.execute("TRUNCATE class_os_gate.scope_receipt_payload")
