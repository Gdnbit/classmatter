from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


ROLE = "class_os_spike"
DATABASE = "class_os_spike"
PRIMARY_PORT = 55432
RESTORE_PORT = 55433


def checked_path(root: Path, name: str) -> Path:
    root = root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise RuntimeError(f"unsafe runtime path: {path}")
    return path


def run(
    command: list[str],
    *,
    timeout: float = 60,
    expect_success: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    io_options = {"capture_output": True} if capture else {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        **io_options,
    )
    if expect_success and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {command[0]}\n{result.stderr}")
    return result


def assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"port already in use: {port}")


def exe(pg_root: Path, name: str) -> str:
    path = pg_root / "bin" / f"{name}.exe"
    if not path.is_file():
        raise RuntimeError(f"missing PostgreSQL binary: {path}")
    return str(path)


def init_cluster(pg_root: Path, data: Path) -> None:
    run([exe(pg_root, "initdb"), "-D", str(data), "-U", ROLE, "--auth=trust", "--encoding=UTF8", "--locale=C"], timeout=90)


def start_cluster(pg_root: Path, data: Path, log: Path, port: int) -> float:
    started = time.perf_counter()
    run(
        [
            exe(pg_root, "pg_ctl"), "-D", str(data), "-l", str(log),
            "-o", f"-p {port} -h 127.0.0.1 -c shared_buffers=64MB -c max_connections=20",
            "start", "-w", "-t", "30",
        ],
        timeout=45,
        capture=False,
    )
    return round((time.perf_counter() - started) * 1000, 3)


def stop_cluster(pg_root: Path, data: Path) -> float:
    if not (data / "postmaster.pid").exists():
        return 0.0
    started = time.perf_counter()
    run([exe(pg_root, "pg_ctl"), "-D", str(data), "stop", "-m", "fast", "-w", "-t", "30"], timeout=45)
    return round((time.perf_counter() - started) * 1000, 3)


def psql(pg_root: Path, port: int, sql: str) -> str:
    return run(
        [exe(pg_root, "psql"), "-h", "127.0.0.1", "-p", str(port), "-U", ROLE, "-d", DATABASE, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        timeout=15,
    ).stdout.strip()


def snapshot(pg_root: Path, port: int) -> str:
    return psql(
        pg_root,
        port,
        "SELECT json_agg(row_to_json(t) ORDER BY task_id)::text FROM (SELECT * FROM task_projection) t;",
    )


def process_tree_rss_mb(data: Path) -> float:
    master_pid = int((data / "postmaster.pid").read_text(encoding="utf-8").splitlines()[0])
    process = psutil.Process(master_pid)
    rss = process.memory_info().rss + sum(child.memory_info().rss for child in process.children(recursive=True))
    return round(rss / (1024 * 1024), 3)


def directory_mb(path: Path) -> float:
    size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return round(size / (1024 * 1024), 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()

    pg_root = args.pg_root.resolve()
    runtime = args.runtime_root.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    primary = checked_path(runtime, "primary-data")
    restored = checked_path(runtime, "restore-data")
    primary_log = checked_path(runtime, "primary.log")
    restore_log = checked_path(runtime, "restore.log")
    backup = checked_path(runtime, "class-os-spike.dump")
    for port in (PRIMARY_PORT, RESTORE_PORT):
        assert_port_free(port)
    for target in (primary, restored):
        if target.exists():
            shutil.rmtree(target)
    for target in (primary_log, restore_log, backup):
        if target.exists():
            target.unlink()

    primary_running = False
    restore_running = False
    evidence: dict[str, object] = {}
    try:
        version = run([exe(pg_root, "postgres"), "--version"]).stdout.strip()
        init_cluster(pg_root, primary)
        cold_start_ms = start_cluster(pg_root, primary, primary_log, PRIMARY_PORT)
        primary_running = True
        run([exe(pg_root, "createdb"), "-h", "127.0.0.1", "-p", str(PRIMARY_PORT), "-U", ROLE, DATABASE])
        schema = Path(__file__).with_name("schema.sql")
        run([exe(pg_root, "psql"), "-h", "127.0.0.1", "-p", str(PRIMARY_PORT), "-U", ROLE, "-d", DATABASE, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(schema)])
        before = snapshot(pg_root, PRIMARY_PORT)
        row_count = int(psql(pg_root, PRIMARY_PORT, "SELECT count(*) FROM task_projection;"))
        rss_mb = process_tree_rss_mb(primary)
        data_mb = directory_mb(primary)
        psutil.cpu_percent(interval=None)
        cpu_started = time.perf_counter()
        cpu_probe_result = psql(pg_root, PRIMARY_PORT, "SELECT sum(i) FROM generate_series(1, 5000000) AS i;")
        cpu_wall_seconds = time.perf_counter() - cpu_started
        host_cpu_percent = psutil.cpu_percent(interval=None)
        if cpu_probe_result != "12500002500000":
            raise RuntimeError("CPU probe returned unexpected result")

        stop_cluster(pg_root, primary)
        primary_running = False
        restart_ms = start_cluster(pg_root, primary, primary_log, PRIMARY_PORT)
        primary_running = True
        after_restart = snapshot(pg_root, PRIMARY_PORT)
        if after_restart != before:
            raise RuntimeError("restart persistence mismatch")

        backup_started = time.perf_counter()
        run([exe(pg_root, "pg_dump"), "-h", "127.0.0.1", "-p", str(PRIMARY_PORT), "-U", ROLE, "-d", DATABASE, "-Fc", "-f", str(backup)])
        backup_ms = round((time.perf_counter() - backup_started) * 1000, 3)
        backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()

        stop_cluster(pg_root, primary)
        primary_running = False
        outage = run(
            [exe(pg_root, "psql"), "-h", "127.0.0.1", "-p", str(PRIMARY_PORT), "-U", ROLE, "-d", DATABASE, "-X", "-A", "-t", "-c", "SELECT 1;"],
            timeout=5,
            expect_success=False,
        )
        if outage.returncode == 0:
            raise RuntimeError("database outage incorrectly returned success")

        init_cluster(pg_root, restored)
        restore_start_ms = start_cluster(pg_root, restored, restore_log, RESTORE_PORT)
        restore_running = True
        run([exe(pg_root, "createdb"), "-h", "127.0.0.1", "-p", str(RESTORE_PORT), "-U", ROLE, DATABASE])
        restore_started = time.perf_counter()
        run([exe(pg_root, "pg_restore"), "-h", "127.0.0.1", "-p", str(RESTORE_PORT), "-U", ROLE, "-d", DATABASE, "--exit-on-error", str(backup)])
        restore_ms = round((time.perf_counter() - restore_started) * 1000, 3)
        after_restore = snapshot(pg_root, RESTORE_PORT)
        if after_restore != before:
            raise RuntimeError("backup restore content mismatch")

        evidence = {
            "schema": "class-os.self-host-spike-evidence/v1",
            "observed_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "postgres_version": version,
            "binary_archive_sha256": "1df55002afe95b945d934c078b13e82c1603fa546731e511d068aa983b4ead28",
            "synthetic_only": True,
            "task_row_count": row_count,
            "restart_content_equal": after_restart == before,
            "restore_content_equal": after_restore == before,
            "outage_failed_closed": outage.returncode != 0,
            "business_commit_via_agent": 0,
            "environment_findings": {
                "docker_desktop": "blocked-host-stale-inference-socket-error-1920",
                "non_ascii_cluster_path": "rejected-by-windows-postgresql-build",
                "database_outage": "failed-closed",
            },
            "host": {
                "logical_cpu_count": psutil.cpu_count(logical=True),
                "physical_cpu_count": psutil.cpu_count(logical=False),
                "total_memory_mb": round(psutil.virtual_memory().total / (1024 * 1024), 3),
            },
            "measurements": {
                "cold_start_ms": cold_start_ms,
                "restart_ms": restart_ms,
                "backup_ms": backup_ms,
                "restore_cluster_start_ms": restore_start_ms,
                "restore_ms": restore_ms,
                "postgres_process_tree_rss_mb": rss_mb,
                "cpu_probe_wall_ms": round(cpu_wall_seconds * 1000, 3),
                "host_cpu_percent_during_probe": host_cpu_percent,
                "primary_data_mb": data_mb,
                "backup_bytes": backup.stat().st_size,
                "backup_sha256": backup_sha,
            },
            "limitations": [
                "Portable PostgreSQL-only drill; Docker Desktop was unavailable because of a host runtime socket failure.",
                "No API, Web, object store, TLS, auth, concurrent load, real data or production retention policy.",
                "Single Windows host measurements are not production capacity or RTO commitments.",
            ],
        }
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    finally:
        if primary_running:
            stop_cluster(pg_root, primary)
        if restore_running:
            stop_cluster(pg_root, restored)
        for target in (primary, restored):
            if target.exists():
                shutil.rmtree(target)
        for target in (primary_log, restore_log, backup):
            if target.exists():
                target.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
