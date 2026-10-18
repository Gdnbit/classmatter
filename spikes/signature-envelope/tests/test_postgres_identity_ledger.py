from __future__ import annotations

import importlib.metadata
import json
import traceback
from pathlib import Path

import pytest

from postgres_identity_ledger import (
    MIGRATION_PATH,
    PostgresIdentityLedger,
    migration_sha256,
)
from signature_envelope import AdmissionError


def test_migration_declares_database_enforced_identity_and_nonce_uniqueness():
    sql = Path(MIGRATION_PATH).read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS class_os_gate" in sql
    assert "CONSTRAINT artifact_identity_ledger_pkey PRIMARY KEY (artifact_id)" in sql
    assert "CONSTRAINT artifact_identity_ledger_nonce_key UNIQUE (nonce)" in sql
    assert "payload_digest character(64) NOT NULL" in sql
    assert "CHECK (nonce ~ '^[0-9a-f]{32}$')" in sql
    assert "CHECK (payload_digest ~ '^[0-9a-f]{64}$')" in sql
    assert len(migration_sha256()) == 64


@pytest.mark.parametrize(
    ("artifact_id", "nonce", "digest", "message"),
    [
        ("", "0" * 32, "1" * 64, "artifact id"),
        ("bad/id", "0" * 32, "1" * 64, "artifact id"),
        ("artifact-1", "ABC", "1" * 64, "nonce"),
        ("artifact-1", "0" * 32, "xyz", "digest"),
    ],
)
def test_invalid_identity_is_rejected_before_connecting(artifact_id, nonce, digest, message):
    called = False

    def forbidden_connect(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("connection must not be attempted")

    ledger = PostgresIdentityLedger("postgresql://synthetic.invalid/db", connect=forbidden_connect)
    with pytest.raises(AdmissionError, match=message):
        ledger.observe(artifact_id, nonce, digest)
    assert called is False


def test_database_failure_is_redacted_and_fails_closed():
    def broken_connect(*_args, **_kwargs):
        raise RuntimeError("postgresql://user:secret@host/private")

    ledger = PostgresIdentityLedger("postgresql://user:secret@host/private", connect=broken_connect)
    with pytest.raises(AdmissionError, match="identity ledger unavailable") as caught:
        ledger.observe("artifact-1", "0" * 32, "1" * 64)
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    rendered = "".join(traceback.format_exception(caught.value))
    assert "secret" not in rendered


@pytest.mark.parametrize("timeout", [0, -1, 60_001])
def test_invalid_operation_timeout_is_rejected(timeout):
    with pytest.raises(AdmissionError, match="operation timeout"):
        PostgresIdentityLedger("postgresql://synthetic.invalid/db", operation_timeout_ms=timeout)


def test_live_evidence_matches_locked_adapter_and_migration():
    evidence_path = Path(__file__).parents[1] / "evidence/postgres-identity-ledger.latest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema"] == "class-os.postgres-artifact-identity-ledger-evidence/v1"
    assert evidence["synthetic_only"] is True
    assert evidence["production_authorization"] is False
    assert evidence["psycopg_version"] == importlib.metadata.version("psycopg") == "3.3.6"
    assert evidence["migration_sha256"] == migration_sha256()
    for source_name in (
        "postgres_identity_ledger.py",
        "postgres_ledger_drill.py",
        "tests/test_postgres_identity_ledger.py",
        "../self-host/portable_recovery.py",
    ):
        source = (Path(__file__).parents[1] / source_name).resolve()
        assert evidence["source_sha256"][source_name] == __import__("hashlib").sha256(
            source.read_bytes()
        ).hexdigest()
    assert evidence["concurrent_idempotent_calls"] == 12
    assert evidence["concurrent_idempotent_all_equal"] is True
    assert evidence["same_artifact_id_conflict_failed_closed"] is True
    assert evidence["same_nonce_conflict_failed_closed"] is True
    assert evidence["conflicting_transaction_left_partial_row"] is False
    assert evidence["restart_persistence_equal"] is True
    assert evidence["restart_projection_equal"] is True
    assert evidence["crash_recovery_projection_equal"] is True
    assert len(evidence["row_projection_sha256"]) == 64
    assert evidence["crash_recovery_projection_sha256"] == evidence["row_projection_sha256"]
    assert len(evidence["schema_contract_sha256"]) == 64
    assert evidence["crash_recovery_schema_contract_sha256"] == evidence["schema_contract_sha256"]
    assert evidence["hostile_schema_failed_closed"] is True
    assert evidence["trigger_schema_failed_closed"] is True
    assert evidence["rule_schema_failed_closed"] is True
    assert evidence["deferrable_constraint_failed_closed"] is True
    assert evidence["unvalidated_constraint_failed_closed"] is True
    assert evidence["unlogged_table_failed_closed"] is True
    assert evidence["weakened_check_failed_closed"] is True
    assert evidence["lock_timeout_failed_closed"] is True
    assert evidence["cleanup_completed_before_evidence_write"] is True
    assert evidence["row_count_before_restart"] == evidence["row_count_after_restart"] == 3
    assert evidence["outage_failed_closed"] is True
