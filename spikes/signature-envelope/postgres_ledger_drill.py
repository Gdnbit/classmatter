from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from postgres_identity_ledger import (
    PostgresIdentityLedger,
    migration_sha256,
    schema_contract_sha256,
    source_sha256,
)
from signature_envelope import AdmissionError


SPIKE_ROOT = Path(__file__).resolve().parent
SELF_HOST_ROOT = SPIKE_ROOT.parent / "self-host"
PORTABLE_RECOVERY_PATH = SELF_HOST_ROOT / "portable_recovery.py"
sys.path.insert(0, str(SELF_HOST_ROOT))

from portable_recovery import (  # noqa: E402
    DATABASE,
    ROLE,
    assert_port_free,
    checked_path,
    exe,
    init_cluster,
    run,
    start_cluster,
    stop_cluster,
)


PORT = 55434
OWNERSHIP_MARKER = ".class-os-artifact-ledger-run"
OWNERSHIP_VALUE = "class-os-artifact-ledger-spike/v1\n"


def concurrent_outcomes(calls) -> list[str]:
    def invoke(arguments) -> str:
        ledger, artifact_id, nonce, digest = arguments
        try:
            ledger.observe(artifact_id, nonce, digest)
            return "ok"
        except AdmissionError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=min(12, len(calls))) as pool:
        return list(pool.map(invoke, calls))


def database_snapshot(conninfo: str) -> tuple[list[list[str]], str, str]:
    with psycopg.connect(conninfo, connect_timeout=3) as connection:
        rows = [
            list(row)
            for row in connection.execute(
                """
                SELECT artifact_id, nonce::text, payload_digest::text
                FROM class_os_gate.artifact_identity_ledger
                ORDER BY artifact_id
                """
            ).fetchall()
        ]
        contract_hash = schema_contract_sha256(connection)
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return rows, hashlib.sha256(canonical.encode("utf-8")).hexdigest(), contract_hash


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()

    pg_root = args.pg_root.resolve()
    runtime = args.runtime_root.resolve()
    try:
        str(runtime).encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError("PostgreSQL ledger drill requires an ASCII-only runtime path") from exc
    runtime.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="artifact-ledger-", dir=runtime)).resolve()
    try:
        if not run_root.is_relative_to(runtime) or run_root == runtime:
            raise RuntimeError("unsafe PostgreSQL ledger run directory")
        marker = checked_path(run_root, OWNERSHIP_MARKER)
        marker.write_text(OWNERSHIP_VALUE, encoding="ascii", newline="\n")
        data = checked_path(run_root, "data")
        log = checked_path(run_root, "postgres.log")
    except BaseException:
        if run_root.is_relative_to(runtime) and run_root != runtime and run_root.exists():
            shutil.rmtree(run_root)
        raise
    running = False
    evidence: dict[str, object] | None = None
    work_error: BaseException | None = None
    try:
        assert_port_free(PORT)
        postgres_version = run([exe(pg_root, "postgres"), "--version"]).stdout.strip()
        init_cluster(pg_root, data)
        start_cluster(pg_root, data, log, PORT)
        running = True
        run(
            [
                exe(pg_root, "createdb"),
                "-h",
                "127.0.0.1",
                "-p",
                str(PORT),
                "-U",
                ROLE,
                DATABASE,
            ]
        )
        conninfo = f"host=127.0.0.1 port={PORT} user={ROLE} dbname={DATABASE}"
        ledger = PostgresIdentityLedger(conninfo)

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute("CREATE SCHEMA class_os_gate")
            connection.execute(
                """
                CREATE TABLE class_os_gate.artifact_identity_ledger (
                    artifact_id text PRIMARY KEY,
                    nonce character(32) NOT NULL,
                    payload_digest character(64) NOT NULL,
                    first_observed_at timestamp with time zone NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
        hostile_schema_failed_closed = False
        try:
            ledger.migrate()
        except AdmissionError as exc:
            hostile_schema_failed_closed = str(exc) == "artifact identity ledger schema contract mismatch"
        if not hostile_schema_failed_closed:
            raise RuntimeError("hostile pre-existing schema did not fail closed")
        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute("DROP SCHEMA class_os_gate CASCADE")

        ledger.migrate()
        ledger.migrate()

        def schema_rejection_observed() -> bool:
            try:
                ledger.migrate()
            except AdmissionError as exc:
                return str(exc) == "artifact identity ledger schema contract mismatch"
            return False

        def reset_schema() -> None:
            with psycopg.connect(conninfo, connect_timeout=3) as connection:
                connection.execute("DROP SCHEMA class_os_gate CASCADE")
            ledger.migrate()

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute(
                """
                CREATE FUNCTION class_os_gate.rewrite_artifact_identity()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    NEW.artifact_id := 'rewritten-by-trigger';
                    RETURN NEW;
                END
                $$
                """
            )
            connection.execute(
                """
                CREATE TRIGGER rewrite_artifact_identity
                BEFORE INSERT ON class_os_gate.artifact_identity_ledger
                FOR EACH ROW EXECUTE FUNCTION class_os_gate.rewrite_artifact_identity()
                """
            )
        trigger_schema_failed_closed = schema_rejection_observed()
        if not trigger_schema_failed_closed:
            raise RuntimeError("identity rewrite trigger did not fail schema contract")
        reset_schema()

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute("CREATE TABLE class_os_gate.rule_sink (artifact_id text NOT NULL)")
            connection.execute(
                """
                CREATE RULE duplicate_identity_to_sink AS
                ON INSERT TO class_os_gate.artifact_identity_ledger
                DO ALSO INSERT INTO class_os_gate.rule_sink (artifact_id) VALUES (NEW.artifact_id)
                """
            )
        rule_schema_failed_closed = schema_rejection_observed()
        if not rule_schema_failed_closed:
            raise RuntimeError("identity rewrite rule did not fail schema contract")
        reset_schema()

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute(
                """
                ALTER TABLE class_os_gate.artifact_identity_ledger
                DROP CONSTRAINT artifact_identity_ledger_nonce_key
                """
            )
            connection.execute(
                """
                ALTER TABLE class_os_gate.artifact_identity_ledger
                ADD CONSTRAINT artifact_identity_ledger_nonce_key UNIQUE (nonce)
                DEFERRABLE INITIALLY DEFERRED
                """
            )
        deferrable_constraint_failed_closed = schema_rejection_observed()
        if not deferrable_constraint_failed_closed:
            raise RuntimeError("deferrable identity constraint did not fail schema contract")
        reset_schema()

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute(
                """
                ALTER TABLE class_os_gate.artifact_identity_ledger
                DROP CONSTRAINT artifact_identity_ledger_artifact_id_format
                """
            )
            connection.execute(
                """
                ALTER TABLE class_os_gate.artifact_identity_ledger
                ADD CONSTRAINT artifact_identity_ledger_artifact_id_format
                CHECK (artifact_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') NOT VALID
                """
            )
        unvalidated_constraint_failed_closed = schema_rejection_observed()
        if not unvalidated_constraint_failed_closed:
            raise RuntimeError("unvalidated identity constraint did not fail schema contract")
        reset_schema()

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute("DROP TABLE class_os_gate.artifact_identity_ledger")
            migration_sql = (SPIKE_ROOT / "migrations/001_artifact_identity_ledger.sql").read_text(
                encoding="utf-8"
            )
            connection.execute(
                migration_sql.replace(
                    "CREATE TABLE IF NOT EXISTS class_os_gate.artifact_identity_ledger",
                    "CREATE UNLOGGED TABLE IF NOT EXISTS class_os_gate.artifact_identity_ledger",
                )
            )
        unlogged_table_failed_closed = schema_rejection_observed()
        if not unlogged_table_failed_closed:
            raise RuntimeError("unlogged identity table did not fail schema contract")
        reset_schema()

        with psycopg.connect(conninfo, connect_timeout=3) as connection:
            connection.execute(
                """
                ALTER TABLE class_os_gate.artifact_identity_ledger
                DROP CONSTRAINT artifact_identity_ledger_artifact_id_format
                """
            )
            connection.execute(
                """
                ALTER TABLE class_os_gate.artifact_identity_ledger
                ADD CONSTRAINT artifact_identity_ledger_artifact_id_format
                CHECK (artifact_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$' OR true)
                """
            )
        weakened_check_failed_closed = schema_rejection_observed()
        if not weakened_check_failed_closed:
            raise RuntimeError("weakened CHECK expression did not fail schema contract")
        reset_schema()

        same_call = (
            ledger,
            "artifact-idempotent-001",
            "00000000000000000000000000000001",
            "1" * 64,
        )
        idempotent = concurrent_outcomes([same_call] * 12)
        if idempotent != ["ok"] * 12:
            raise RuntimeError(f"concurrent idempotency failed: {idempotent}")

        same_id_race = concurrent_outcomes(
            [
                (
                    ledger,
                    "artifact-id-race-001",
                    "00000000000000000000000000000002",
                    digit * 64,
                )
                for digit in ("2", "3")
            ]
        )
        if same_id_race.count("ok") != 1 or sum(
            "artifact id collision" in item for item in same_id_race
        ) != 1:
            raise RuntimeError(f"artifact-id race did not fail closed: {same_id_race}")

        same_nonce_race = concurrent_outcomes(
            [
                (
                    ledger,
                    artifact_id,
                    "00000000000000000000000000000003",
                    digest,
                )
                for artifact_id, digest in (
                    ("artifact-nonce-race-a", "4" * 64),
                    ("artifact-nonce-race-b", "5" * 64),
                )
            ]
        )
        if same_nonce_race.count("ok") != 1 or sum(
            "nonce collision" in item for item in same_nonce_race
        ) != 1:
            raise RuntimeError(f"nonce race did not fail closed: {same_nonce_race}")

        blocker = psycopg.connect(conninfo, connect_timeout=3)
        try:
            blocker.execute(
                """
                INSERT INTO class_os_gate.artifact_identity_ledger
                    (artifact_id, nonce, payload_digest)
                VALUES (%s, %s, %s)
                """,
                ("artifact-lock-001", "00000000000000000000000000000004", "6" * 64),
            )
            timed_ledger = PostgresIdentityLedger(conninfo, operation_timeout_ms=350)
            started = time.perf_counter()
            try:
                timed_ledger.observe(
                    "artifact-lock-001", "00000000000000000000000000000004", "6" * 64
                )
                lock_timeout_failed_closed = False
            except AdmissionError as exc:
                elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                lock_timeout_failed_closed = (
                    str(exc) == "artifact identity ledger unavailable" and elapsed_ms < 2500
                )
        finally:
            blocker.rollback()
            blocker.close()
        if not lock_timeout_failed_closed:
            raise RuntimeError("conflicting uncommitted row did not fail closed within timeout")

        rows_before_restart, projection_hash_before, contract_hash_before = database_snapshot(conninfo)
        row_count_before_restart = len(rows_before_restart)
        if row_count_before_restart != 3:
            raise RuntimeError("conflicting requests left a partial ledger row")

        stop_cluster(pg_root, data)
        running = False
        start_cluster(pg_root, data, log, PORT)
        running = True
        restarted = PostgresIdentityLedger(conninfo)
        restarted.observe(*same_call[1:])
        rows_after_restart, projection_hash_after, contract_hash_after = database_snapshot(conninfo)
        row_count_after_restart = len(rows_after_restart)
        if rows_after_restart != rows_before_restart:
            raise RuntimeError("identity ledger changed across restart")
        if contract_hash_after != contract_hash_before:
            raise RuntimeError("identity ledger schema contract changed across restart")

        run([exe(pg_root, "pg_ctl"), "-D", str(data), "stop", "-m", "immediate", "-w", "-t", "30"])
        running = False
        start_cluster(pg_root, data, log, PORT)
        running = True
        rows_after_crash, projection_hash_after_crash, contract_hash_after_crash = database_snapshot(
            conninfo
        )
        if rows_after_crash != rows_before_restart or contract_hash_after_crash != contract_hash_before:
            raise RuntimeError("identity ledger changed across immediate-stop recovery")

        stop_cluster(pg_root, data)
        running = False
        outage_failed_closed = False
        try:
            restarted.observe(
                "artifact-outage-001",
                "00000000000000000000000000000005",
                "7" * 64,
            )
        except AdmissionError as exc:
            outage_failed_closed = str(exc) == "artifact identity ledger unavailable"
        if not outage_failed_closed:
            raise RuntimeError("database outage did not fail closed")

        evidence = {
            "schema": "class-os.postgres-artifact-identity-ledger-evidence/v1",
            "observed_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "synthetic_only": True,
            "postgres_version": postgres_version,
            "psycopg_version": importlib.metadata.version("psycopg"),
            "migration_sha256": migration_sha256(),
            "source_sha256": {
                "postgres_identity_ledger.py": source_sha256(SPIKE_ROOT / "postgres_identity_ledger.py"),
                "postgres_ledger_drill.py": source_sha256(Path(__file__)),
                "tests/test_postgres_identity_ledger.py": source_sha256(
                    SPIKE_ROOT / "tests/test_postgres_identity_ledger.py"
                ),
                "../self-host/portable_recovery.py": source_sha256(PORTABLE_RECOVERY_PATH),
            },
            "port": PORT,
            "concurrent_idempotent_calls": len(idempotent),
            "concurrent_idempotent_all_equal": idempotent == ["ok"] * len(idempotent),
            "same_artifact_id_conflict_failed_closed": True,
            "same_nonce_conflict_failed_closed": True,
            "conflicting_transaction_left_partial_row": False,
            "row_count_before_restart": row_count_before_restart,
            "row_count_after_restart": row_count_after_restart,
            "restart_persistence_equal": row_count_after_restart == row_count_before_restart,
            "restart_projection_equal": rows_after_restart == rows_before_restart,
            "crash_recovery_projection_equal": rows_after_crash == rows_before_restart,
            "row_projection_sha256": projection_hash_after,
            "crash_recovery_projection_sha256": projection_hash_after_crash,
            "schema_contract_sha256": contract_hash_after,
            "crash_recovery_schema_contract_sha256": contract_hash_after_crash,
            "hostile_schema_failed_closed": hostile_schema_failed_closed,
            "trigger_schema_failed_closed": trigger_schema_failed_closed,
            "rule_schema_failed_closed": rule_schema_failed_closed,
            "deferrable_constraint_failed_closed": deferrable_constraint_failed_closed,
            "unvalidated_constraint_failed_closed": unvalidated_constraint_failed_closed,
            "unlogged_table_failed_closed": unlogged_table_failed_closed,
            "weakened_check_failed_closed": weakened_check_failed_closed,
            "lock_timeout_failed_closed": lock_timeout_failed_closed,
            "lock_timeout_observed_ms": elapsed_ms,
            "outage_failed_closed": outage_failed_closed,
            "production_authorization": False,
            "cleanup_completed_before_evidence_write": False,
            "limitations": [
                "Single-host portable PostgreSQL synthetic drill, not a production topology or capacity test.",
                "Proves artifact identity/nonce uniqueness only; does not consume setup or allocate a workspace.",
                "Trust authentication is confined to the temporary loopback-only spike cluster.",
            ],
        }
    except BaseException as exc:
        work_error = exc
    finally:
        cleanup_errors: list[str] = []
        cluster_pid_exists = data.exists() and (data / "postmaster.pid").exists()
        if cluster_pid_exists:
            try:
                stop_cluster(pg_root, data)
                running = False
            except Exception:
                cleanup_errors.append("postgres stop failed")
        cluster_pid_exists = data.exists() and (data / "postmaster.pid").exists()
        if not cluster_pid_exists:
            try:
                if marker.read_text(encoding="ascii") != OWNERSHIP_VALUE:
                    raise RuntimeError("ownership marker mismatch")
                shutil.rmtree(run_root)
            except Exception:
                cleanup_errors.append("owned run-directory cleanup failed")
    if cleanup_errors:
        raise RuntimeError("artifact ledger drill cleanup failed")
    if work_error is not None:
        raise work_error
    if evidence is None:
        raise RuntimeError("artifact ledger drill produced no evidence")
    evidence["cleanup_completed_before_evidence_write"] = True
    if args.evidence:
        write_json_atomic(args.evidence, evidence)
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
