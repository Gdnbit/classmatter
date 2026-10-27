"""Runtime composition and Windows protected-secret smoke, no real records."""
import os
import json
from pathlib import Path
import secrets

import httpx
import pytest

from class_os.infrastructure.local_runtime import LocalRuntime, ROOT, D1_ROOT, PROFILES, compose, protect
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.interfaces.http.settings import Settings
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pwdlib import PasswordHash
from class_os.application.identity import IdentityBoundary
from class_os.application.roster import BusinessGateway, QueryGateway
from class_os.domain.activity import CreateTask
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.roster import PostgresBusinessStore
from test_activity_gateway import seed, submit
from test_identity import setup, CLIENT


def test_runtime_root_is_ignored_repository_local_not_parent():
    assert ROOT == Path(__file__).resolve().parents[2] / ".local-runtime/synthetic-v1"
    assert LocalRuntime().root == ROOT.resolve() and LocalRuntime().profile == "r1"
    assert LocalRuntime(profile="conversation-d1").root == D1_ROOT.resolve()
    for wrong in ("", "latest", "head", "production"):
        with pytest.raises(ValueError):
            LocalRuntime(profile=wrong)
    for root, profile in ((ROOT, "conversation-d1"), (D1_ROOT, "r1")):
        with pytest.raises(ValueError):
            LocalRuntime(root, profile=profile)


@pytest.mark.parametrize("profile", ["r1", "conversation-d1"])
def test_runtime_descriptor_never_reinterprets_another_profile(tmp_path, profile):
    runtime = LocalRuntime(tmp_path, profile=profile)
    marker, database, _ = PROFILES[profile]
    descriptor = {"profile": marker, "database": database, "pg_bin": "synthetic-bin", "port": 5555}
    runtime.manifest.write_text(json.dumps(descriptor), encoding="utf-8")
    assert runtime.configuration() == descriptor
    other = "r1" if profile != "r1" else "conversation-d1"
    with pytest.raises(RuntimeError):
        LocalRuntime(tmp_path, profile=other).configuration()
    for invalid in ({**descriptor, "profile": PROFILES[other][0]},
                    {**descriptor, "database": PROFILES[other][1]},
                    {**descriptor, "schema": "head"}, {**descriptor, "port": True}):
        runtime.manifest.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises(RuntimeError):
            runtime.configuration()
    if profile == "conversation-d1":
        with pytest.raises(ValueError):
            compose(Settings(), runtime)


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Windows owned D1 SCRAM/DPAPI runtime")
def test_fresh_explicit_d1_owned_profile_restart_does_not_initialize_owner_or_control(tmp_path, request):
    from sqlalchemy import text
    from class_os.infrastructure.persistence.schema_inventory import validate_surface
    runtime = LocalRuntime(tmp_path / "isolated-conversation-d1", profile="conversation-d1")
    runtime.initialize(request.config.getoption("--pg-root"))
    running = False
    try:
        for _ in range(2):
            runtime.start(); running = True
            database = runtime.database("migrator")
            try:
                assert database.profile == "conversation-d1"
                with database.transaction(read_only=True) as connection:
                    assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0026"
                    assert len(validate_surface(connection, complete=True, profile="conversation-d1")) == 35
                    assert connection.execute(text("SELECT count(*) FROM class_os.owner_account")).scalar_one() == 0
                    assert connection.execute(text("SELECT count(*) FROM class_os.conversation_control")).scalar_one() == 0
            finally:
                database.close()
            runtime.stop(); running = False
        with pytest.raises(RuntimeError):
            LocalRuntime(runtime.root).configuration()
        assert not (runtime.root / "conversation-restrictions.dpapi").exists()
    finally:
        if running:
            runtime.stop()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI profile")
def test_current_user_dpapi_roundtrip_and_no_plaintext():
    value = secrets.token_bytes(48)
    protected = protect(value)
    assert value not in protected
    assert protect(protected, decrypt=True) == value
    with pytest.raises(RuntimeError):
        protect(b"invalid", decrypt=True)


@pytest.mark.db
@pytest.mark.asyncio
async def test_supported_composition_ready_and_database_failure(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)

    class FixtureRuntime:
        def database(self, role):
            assert role in {"identity", "runtime"}
            return Database(database_urls[role], identity=role == "identity")

    app = compose(Settings(), FixtureRuntime())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        assert (await client.get("/health/ready")).status_code == 200
        assert (await client.get("/api/identity/context")).status_code == 200
        assert (await client.get("/api/identity/session")).status_code == 401
    owner.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Windows operator profile")
@pytest.mark.parametrize("directory", ["owned-runtime", "合成运行目录"])
def test_owned_runtime_restart_with_scram_and_no_plaintext(tmp_path, request, directory):
    runtime = LocalRuntime(tmp_path / directory)
    runtime.initialize(request.config.getoption("--pg-root"))
    config = runtime.configuration()
    assert "trust" not in (runtime.cluster / "pg_hba.conf").read_text(encoding="utf-8")
    assert set(config) == {"profile", "pg_bin", "port", "database"}
    with pytest.raises(RuntimeError):
        runtime.initialize(request.config.getoption("--pg-root"))
    runtime.start()
    try:
        db = runtime.database("runtime")
        with db.transaction(read_only=True) as connection:
            from sqlalchemy import text
            assert connection.execute(text("SELECT data_mode FROM class_os.database_state")).scalar_one() == "synthetic-only"
        db.close()
    finally:
        runtime.stop()


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Windows owned SCRAM/DPAPI runtime")
def test_owned_business_entities_survive_actual_pg_process_restart(tmp_path, request):
    runtime = LocalRuntime(tmp_path / "合成业务重启")
    runtime.initialize(request.config.getoption("--pg-root"))
    clock = [datetime(2026, 10, 8, 12, tzinfo=timezone.utc)]

    @contextmanager
    def gateways():
        identity_db = runtime.database("identity")
        business_db = runtime.database("runtime")
        try:
            boundary = IdentityBoundary(PostgresIdentityStore(identity_db), PasswordHash.recommended(), clock=lambda: clock[0])
            store = PostgresBusinessStore(business_db)
            yield (BusinessGateway(boundary, store, clock=lambda: clock[0]),
                   QueryGateway(boundary, store, clock=lambda: clock[0]), store, boundary)
        finally:
            business_db.close()
            identity_db.close()

    running = False
    try:
        runtime.start(); running = True
        with gateways() as (business, query, store, boundary):
            auth = setup(boundary)
            credentials = (auth.token, CLIENT, auth.csrf, auth.subject.workspace_id)
            classroom, student, record = seed((business, query, store, credentials, boundary, None, clock))
            submit(business, credentials, record)
            task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
                              "合成PG重启跟进", clock[0] + timedelta(minutes=5), student.student_id, record.record_id)
            submit(business, credentials, task)
            before = query.projection(*credentials, classroom.class_id, classroom.term_id)
        # All pools are closed before stopping ONLY this freshly owned PG.
        runtime.stop(); running = False
        runtime.start(); running = True
        with gateways() as (_, query, _, _):
            after = query.projection(*credentials, classroom.class_id, classroom.term_id)
            assert after == before
            students = query.roster(*credentials, classroom.class_id, classroom.term_id)
            assert [(row.student_id, row.version) for row in students] == [(student.student_id, 1)]
            assert [(row["record_id"], row["version"]) for row in after["records"]] == [(record.record_id, 1)]
            assert [(row["task_id"], row["version"]) for row in after["tasks"]] == [(task.task_id, 1)]
            assert after["tasks"][0]["source_record_id"] == record.record_id
            assert after["tasks"][0]["student_id"] == student.student_id
    finally:
        if running:
            runtime.stop()
