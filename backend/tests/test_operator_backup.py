"""Owned synthetic dumps only; fixture codec is NOT encryption evidence."""
from contextlib import contextmanager
from pathlib import Path
import os
import json
import shutil
from types import SimpleNamespace
import importlib.util
import sys
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text

from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected
from class_os.infrastructure.persistence.database import Database
from test_activity_gateway import seed, submit
from class_os.domain.activity import CreateTask, ReviseRecord
from test_roster_gateway import roster
from test_identity import identity
from test_model_secrets import fixture_codec


@pytest.fixture
def backup_runtime(roster, database_urls, postgres_cluster, request, tmp_path):
    classroom, student, record = seed(roster)
    submit(roster[0], roster[3], record)
    submit(roster[0], roster[3], ReviseRecord("record.correct", record.record_id, classroom.class_id,
                                           classroom.term_id, 1, "合成备份更正事实", "", "合成教师更正"))
    submit(roster[0], roster[3], CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
                                         "合成备份关联任务", student_id=student.student_id, source_record_id=record.record_id))
    binaries = Path(request.config.getoption("--pg-root")).resolve()
    if (binaries / "bin").is_dir():
        binaries /= "bin"
    class FixtureRuntime:
        root = tmp_path / "owned-backups"
        def configuration(self):
            return {"profile": "class-os-owned-synthetic-v1", "pg_bin": str(binaries),
                    "port": postgres_cluster["port"], "database": database_urls["migrator"].database}
        def password(self, role):
            assert role == "migrator"
            return ""  # Disposable trust-auth fixture only.
        def database(self, role):
            assert role == "migrator"
            return Database(database_urls[role], migration=True)
        @contextmanager
        def admin(self):
            with psycopg.connect(**postgres_cluster, autocommit=True) as connection:
                yield connection
    runtime = FixtureRuntime()
    runtime.root.mkdir()
    return runtime


@pytest.mark.db
def test_actual_dump_snapshot_and_isolated_restore_preserve_source(backup_runtime):
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    source = backup_runtime.database("migrator")
    try:
        with source.transaction(read_only=True) as connection:
            before = backup._inventory(connection)
    finally:
        source.close()
    artifact = backup.create()
    assert type(artifact) is UUID
    path = backup_runtime.root / "backups" / (str(artifact) + ".dpapi")
    assert path.is_file()
    source = backup_runtime.database("migrator")
    try:
        with source.transaction(read_only=True) as connection:
            assert backup._inventory(connection) == before
    finally:
        source.close()
    result = backup.check(artifact)
    assert result == {"schema_version": "class-os.synthetic-backup-check.v1", "verified": True,
                      "source_preserved": True, "temporary_clone_removed": True,
                      "portable": False, "complete_exit": False, "table_count": 22}
    source = backup_runtime.database("migrator")
    try:
        with source.transaction(read_only=True) as connection:
            assert backup._inventory(connection) == before
    finally:
        source.close()
    assert path.is_file()
    with backup_runtime.admin() as connection:
        assert not connection.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname LIKE 'class_os_synthetic_restore_%')").fetchone()[0]


@pytest.mark.db
def test_bad_backup_binding_and_restore_failure_leave_source_and_backup(backup_runtime, monkeypatch):
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    artifact = backup.create()
    path = backup_runtime.root / "backups" / (str(artifact) + ".dpapi")
    before = path.read_bytes()
    with pytest.raises(BackupRejected):
        backup.check(uuid4())
    original = backup._pg
    def fail(binary, *args, **kwargs):
        if binary == "pg_restore":
            raise BackupRejected()
        return original(binary, *args, **kwargs)
    monkeypatch.setattr(backup, "_pg", fail)
    with pytest.raises(BackupRejected):
        backup.check(artifact)
    assert path.read_bytes() == before
    source = backup_runtime.database("migrator")
    try:
        with source.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.student")).scalar_one() > 0
    finally:
        source.close()
    with backup_runtime.admin() as connection:
        assert not connection.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname LIKE 'class_os_synthetic_restore_%')").fetchone()[0]


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI backup protection")
def test_actual_dpapi_backup_does_not_store_plaintext_and_rejects_corruption(backup_runtime):
    backup = SyntheticBackup(backup_runtime)
    artifact = backup.create()
    path = backup_runtime.root / "backups" / (str(artifact) + ".dpapi")
    assert b"PGDMP" not in path.read_bytes() and b"synthetic-test-passphrase" not in path.read_bytes()
    assert backup.check(artifact)["verified"]
    # Owned test artifact only; deliberately corrupt the protected bytes.
    blob = bytearray(path.read_bytes()); blob[len(blob) // 2] ^= 1
    path.write_bytes(blob)
    with pytest.raises(BackupRejected):
        backup.check(artifact)


@pytest.mark.db
def test_backup_closed_metadata_wrong_runtime_and_concurrent_source_snapshot(backup_runtime, monkeypatch):
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    original = backup._pg
    changed = []
    def mutate_after_snapshot(binary, *args, **kwargs):
        if binary == "pg_dump":
            source = backup_runtime.database("migrator")
            try:
                with source.transaction() as connection:
                    # A later committed source change must not enter the exported snapshot.
                    connection.execute(text("INSERT INTO class_os.identity_audit(event_id,action,outcome,occurred_at) VALUES(:id,'session','allowed',now())"), {"id": uuid4()})
            finally:
                source.close()
            changed.append(True)
        return original(binary, *args, **kwargs)
    monkeypatch.setattr(backup, "_pg", mutate_after_snapshot)
    artifact = backup.create()
    assert changed == [True] and backup.check(artifact)["verified"]
    path = backup_runtime.root / "backups" / (str(artifact) + ".dpapi")
    sealed = path.read_bytes()
    packet = json.loads(fixture_codec(sealed, decrypt=True))
    for mutate in (lambda value: value.update(head="0001"), lambda value: value.update(binding="0" * 64),
                   lambda value: value.update(unknown=True), lambda value: value.update(archive_sha256="0" * 64),
                   lambda value: value["inventory"].pop("identity_audit")):
        value = json.loads(json.dumps(packet)); mutate(value)
        path.write_bytes(fixture_codec(json.dumps(value).encode()))
        with pytest.raises(BackupRejected):
            backup.check(artifact)
    path.write_bytes(sealed)
    alternate = backup_runtime.root.parent / "another-owned-root"
    (alternate / "backups").mkdir(parents=True)
    shutil.copyfile(path, alternate / "backups" / path.name)
    monkeypatch.setattr(backup_runtime, "root", alternate)
    with pytest.raises(BackupRejected):
        backup.check(artifact)


def test_backup_subprocess_uses_explicit_noninteractive_credentials_not_ambient_env(tmp_path, monkeypatch):
    from class_os.infrastructure import operator_backup
    binary = tmp_path / ("pg_dump.exe" if os.name == "nt" else "pg_dump")
    binary.touch()
    runtime = SimpleNamespace(configuration=lambda: {"pg_bin": str(tmp_path), "port": 5439},
                              password=lambda role: "synthetic-child-only")
    seen = []
    def run(argv, **kwargs):
        seen.append((argv, {**kwargs, "env": kwargs["env"].copy()}))
        return SimpleNamespace(returncode=0, stdout=b"PGDMPsynthetic", stderr=b"")
    monkeypatch.setattr(operator_backup.subprocess, "run", run)
    monkeypatch.setenv("PGSERVICE", "must-not-use")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-read")
    backup = SyntheticBackup(runtime, codec=fixture_codec)
    assert backup._pg("pg_dump", "class_os_synthetic_owned", "--format=custom").startswith(b"PGDMP")
    argv, options = seen[0]
    assert "--no-password" in argv and all("synthetic-child-only" not in value for value in argv)
    assert options["env"]["PGPASSWORD"] == "synthetic-child-only"
    assert "PGSERVICE" not in options["env"] and "OPENAI_API_KEY" not in options["env"]
    assert options["timeout"] == 45 and not options.get("shell", False)


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Owned Windows SCRAM/DPAPI CLI")
def test_actual_operator_cli_owned_scram_runtime(tmp_path, request, monkeypatch, capsys):
    from class_os.infrastructure.local_runtime import LocalRuntime
    runtime = LocalRuntime(tmp_path / "owned-cli-runtime")
    runtime.initialize(request.config.getoption("--pg-root"))
    runtime.start()
    try:
        spec = importlib.util.spec_from_file_location("class_os_test_local_backup_cli", Path(__file__).resolve().parents[1] / "local.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        monkeypatch.setattr("class_os.infrastructure.local_runtime.LocalRuntime", lambda: runtime)
        monkeypatch.setattr(sys, "argv", ["local.py", "backup"])
        assert module.main() == 0
        created = json.loads(capsys.readouterr().out)
        assert created["complete_exit"] is False and created["portable"] is False
        monkeypatch.setattr(sys, "argv", ["local.py", "backup-check", "--backup-id", created["backup_id"]])
        assert module.main() == 0
        assert json.loads(capsys.readouterr().out)["verified"] is True
    finally:
        runtime.stop()
