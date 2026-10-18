"""Isolated live PostgreSQL proof of the synthetic setup allocation transaction."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from scope_allocation import ScopeAllocationStore
from scope_allocation_evidence import LIMITATIONS
from scope_allocation_schema import GOLDEN, snapshot, validate as validate_schema_contract
from signature_envelope import AdmissionError


SPIKE_ROOT = Path(__file__).resolve().parent
SELF_HOST_ROOT = SPIKE_ROOT.parent / "self-host"
sys.path.insert(0, str(SELF_HOST_ROOT))
from portable_recovery import (  # noqa: E402
    DATABASE, ROLE, assert_port_free, checked_path, exe,
    init_cluster, run, start_cluster, stop_cluster,
)


PORT = 55435
WRITER_ROLE = "class_os_scope_writer"
MARKER_NAME = ".class-os-scope-allocation-run"
MARKER_VALUE = "class-os-scope-allocation-spike/v1\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def projection(conninfo: str) -> tuple[list[int], str]:
    tables = (
        "scope_setup_consumption", "scope_allocation", "scope_allocation_ledger",
        "scope_allocation_audit", "scope_receipt_payload",
    )
    with psycopg.connect(conninfo, connect_timeout=3) as connection:
        rows_by_table = {
            table: [row[0] for row in connection.execute(
                f"SELECT to_jsonb(t) FROM class_os_gate.{table} AS t "
                "ORDER BY deployment_id, setup_artifact_id"
            ).fetchall()]
            for table in tables
        }
    counts = [len(rows_by_table[table]) for table in tables]
    encoded = json.dumps(rows_by_table, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return counts, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    parser.add_argument("--evidence", type=Path, default=SPIKE_ROOT / "evidence/scope-allocation.latest.json")
    parser.add_argument("--refresh-schema-contract", action="store_true")
    args = parser.parse_args()

    pg_root = args.pg_root.resolve(strict=True)
    runtime = args.runtime_root.resolve()
    if not runtime.is_absolute() or not str(runtime).isascii():
        raise RuntimeError("scope allocation drill requires an absolute ASCII-only runtime path")
    runtime.mkdir(parents=True, exist_ok=True)
    created_root = Path(tempfile.mkdtemp(prefix="scope-allocation-", dir=runtime))
    try:
        run_root = created_root.resolve()
        if run_root == runtime or not run_root.is_relative_to(runtime):
            raise RuntimeError("unsafe scope allocation run directory")
    except BaseException:
        # Only an empty directory just returned by mkdtemp is eligible here.
        if created_root.parent == runtime and created_root.is_dir() and not any(created_root.iterdir()):
            created_root.rmdir()
        raise
    marker = run_root / MARKER_NAME
    data: Path | None = None
    evidence: dict[str, object] | None = None
    failure: BaseException | None = None
    try:
        marker = checked_path(run_root, MARKER_NAME)
        marker.write_text(MARKER_VALUE, encoding="ascii", newline="\n")
        data = checked_path(run_root, "data")
        log = checked_path(run_root, "postgres.log")
        assert_port_free(PORT)
        version = run([exe(pg_root, "postgres"), "--version"]).stdout.strip()
        init_cluster(pg_root, data)
        start_cluster(pg_root, data, log, PORT)
        run([
            exe(pg_root, "createdb"), "-h", "127.0.0.1", "-p", str(PORT),
            "-U", ROLE, DATABASE,
        ])
        admin_conninfo = f"host=127.0.0.1 port={PORT} user={ROLE} dbname={DATABASE}"
        with psycopg.connect(admin_conninfo, connect_timeout=3) as connection:
            connection.execute(
                (SPIKE_ROOT / "migrations/002_scope_allocation.sql").read_text(encoding="utf-8")
            )
            if args.refresh_schema_contract:
                GOLDEN.write_text(
                    json.dumps(snapshot(connection), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n",
                )
            validate_schema_contract(connection)
            connection.execute(f"CREATE ROLE {WRITER_ROLE} LOGIN")
            connection.execute(f"GRANT USAGE ON SCHEMA class_os_gate TO {WRITER_ROLE}")
            connection.execute(
                f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA class_os_gate TO {WRITER_ROLE}"
            )
            connection.execute(
                f"GRANT USAGE ON SEQUENCE class_os_gate.scope_allocation_ledger_sequence TO {WRITER_ROLE}"
            )
        conninfo = f"host=127.0.0.1 port={PORT} user={WRITER_ROLE} dbname={DATABASE}"
        env = os.environ.copy()
        env["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_DSN"] = conninfo
        env["CLASS_OS_SCOPE_ALLOCATION_TEST_PG_ADMIN_DSN"] = admin_conninfo
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(SPIKE_ROOT / "tests/test_scope_allocation.py")],
            cwd=SPIKE_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"live scope allocation tests failed:\n{result.stdout}\n{result.stderr}")
        counts_before, hash_before = projection(conninfo)
        if len(set(counts_before)) != 1 or counts_before[0] < 8:
            raise RuntimeError("scope transaction tables diverged after live tests")

        stop_cluster(pg_root, data)
        start_cluster(pg_root, data, log, PORT)
        counts_after, hash_after = projection(conninfo)
        if (counts_after, hash_after) != (counts_before, hash_before):
            raise RuntimeError("scope allocation projection changed after restart")

        stop_cluster(pg_root, data)
        outage_closed = False
        try:
            ScopeAllocationStore(conninfo).counts("deployment-synthetic-001", "setup-synthetic-001")
        except AdmissionError:
            outage_closed = True
        if not outage_closed:
            raise RuntimeError("scope allocation database outage did not fail closed")

        evidence = {
            "schema": "class-os.synthetic-scope-allocation-transaction-evidence/v1",
            "observed_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "synthetic_only": True,
            "production_authorization": False,
            "postgres_version": version,
            "psycopg_version": importlib.metadata.version("psycopg"),
            "migration_sha256": digest(SPIKE_ROOT / "migrations/002_scope_allocation.sql"),
            "schema_contract_sha256": digest(GOLDEN),
            "source_sha256": {
                "scope_allocation.py": digest(SPIKE_ROOT / "scope_allocation.py"),
                "scope_allocation_schema.py": digest(SPIKE_ROOT / "scope_allocation_schema.py"),
                "scope_allocation_drill.py": digest(Path(__file__)),
                "scope_allocation_evidence.py": digest(SPIKE_ROOT / "scope_allocation_evidence.py"),
                "tests/test_scope_allocation.py": digest(SPIKE_ROOT / "tests/test_scope_allocation.py"),
                "tests/test_scope_allocation_evidence.py": digest(
                    SPIKE_ROOT / "tests/test_scope_allocation_evidence.py"
                ),
                "../self-host/portable_recovery.py": digest(SELF_HOST_ROOT / "portable_recovery.py"),
            },
            "live_test_result": result.stdout.strip().splitlines()[-1],
            "five_member_row_counts": counts_after,
            "restart_projection_equal": hash_after == hash_before,
            "five_table_projection_sha256": hash_after,
            "outage_failed_closed": outage_closed,
            "cleanup_completed_before_evidence_write": True,
            "limitations": LIMITATIONS,
        }
    except BaseException as exc:
        failure = exc
    finally:
        cleanup_errors: list[str] = []
        safe_to_remove = True
        if data is not None and data.exists() and (data / "postmaster.pid").exists():
            try:
                stop_cluster(pg_root, data)
            except Exception as exc:
                safe_to_remove = False
                cleanup_errors.append(f"cluster stop failed: {type(exc).__name__}")
        if safe_to_remove and marker.exists() and marker.read_text(encoding="ascii") == MARKER_VALUE:
            if run_root.is_relative_to(runtime) and run_root != runtime:
                try:
                    shutil.rmtree(run_root)
                except Exception as exc:
                    cleanup_errors.append(f"run directory cleanup failed: {type(exc).__name__}")
        elif safe_to_remove:
            cleanup_errors.append("run ownership marker missing or invalid")
        if cleanup_errors:
            raise RuntimeError("; ".join(cleanup_errors)) from failure
    if failure is not None:
        raise failure
    if evidence is None or run_root.exists():
        raise RuntimeError("scope allocation evidence cannot be written before cleanup")
    write_json_atomic(args.evidence.resolve(), evidence)
    print(json.dumps({
        "live_test_result": evidence["live_test_result"],
        "five_member_row_counts": evidence["five_member_row_counts"],
        "cleanup_completed": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
