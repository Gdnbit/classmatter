"""Owned clone ACL faults cannot be hidden behind unchanged content hashes."""
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy import event

from class_os.infrastructure.local_runtime import compose
from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.role_guards import ROLE_NAMES, validate_role_guards
from class_os.interfaces.http.settings import Settings
from test_operator_backup import backup_runtime
from test_roster_gateway import roster
from test_identity import identity


CLONE_FAULTS = (
    "GRANT SELECT ON class_os.owner_account TO class_os_runtime",
    "GRANT SELECT(owner_id) ON class_os.owner_account TO class_os_runtime",
    "GRANT SELECT ON class_os.owner_account TO PUBLIC",
    "GRANT SELECT ON class_os.student TO class_os_identity",
    "GRANT DELETE ON class_os.manual_task TO class_os_runtime",
    "GRANT CREATE ON SCHEMA class_os TO class_os_runtime",
    "GRANT CREATE ON SCHEMA public TO PUBLIC",
    "GRANT SELECT(session_digest) ON class_os.business_audit TO class_os_runtime",
)


@pytest.mark.parametrize("fault", ("missing", "null-flag", "integer-flag", "duplicate", "no-login"))
def test_missing_or_indeterminate_role_metadata_never_passes(fault):
    rows = [{"rolname": role, "rolcanlogin": True, "rolsuper": False, "rolcreatedb": False,
             "rolcreaterole": False, "rolreplication": False, "rolbypassrls": False} for role in ROLE_NAMES]
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(dict(rows[0]))
    elif fault == "no-login":
        rows[0]["rolcanlogin"] = False
    else:
        rows[0]["rolsuper"] = None if fault == "null-flag" else 0
    class Connection:
        calls = 0
        def execute(self, *args):
            self.calls += 1
            assert self.calls == 1, "Invalid role metadata was adopted"
            return self
        def mappings(self):
            return self
        def all(self):
            return rows
    connection = Connection()
    with pytest.raises(RuntimeError, match="Database role safety guards failed"):
        validate_role_guards(connection)
    assert connection.calls == 1


@pytest.mark.db
@pytest.mark.parametrize("fault", CLONE_FAULTS)
def test_restored_clone_with_widened_acl_cannot_pass_matching_content_hashes(backup_runtime, monkeypatch, fault):
    from test_model_secrets import fixture_codec
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    artifact = backup.create()
    packet, _ = backup._open(artifact)
    path = backup_runtime.root / "backups" / (str(artifact) + ".dpapi")
    sealed = path.read_bytes()
    original = backup._pg
    changed = []
    source = backup_runtime.database("migrator")
    try:
        def alter_clone(binary, database, *args, **kwargs):
            result = original(binary, database, *args, **kwargs)
            if binary == "pg_restore":
                assert database.startswith("class_os_synthetic_restore_") and database != source.engine.url.database
                clone = Database(source.engine.url.set(database=database), migration=True)
                try:
                    with clone.transaction() as connection:
                        connection.exec_driver_sql(fault)  # Closed fixture statement, allocated clone only.
                    with clone.transaction(read_only=True) as connection:
                        assert backup._inventory(connection) == packet["inventory"]
                    changed.append(database)
                finally:
                    clone.close()
            return result
        monkeypatch.setattr(backup, "_pg", alter_clone)
        with pytest.raises(BackupRejected):
            backup.check(artifact)
        assert len(changed) == 1 and path.read_bytes() == sealed
        with source.transaction(read_only=True) as connection:
            assert backup._inventory(connection) == packet["inventory"]
            assert connection.execute(text("SELECT has_any_column_privilege('class_os_runtime','class_os.owner_account','SELECT')")).scalar_one() is False
        with backup_runtime.admin() as connection:
            assert connection.execute("SELECT count(*) FROM pg_database WHERE datname=%s", (changed[0],)).fetchone()[0] == 0
    finally:
        source.close()


@pytest.mark.db
@pytest.mark.parametrize("grant,revoke", (("SUPERUSER", "NOSUPERUSER"), ("CREATEDB", "NOCREATEDB"),
                                         ("CREATEROLE", "NOCREATEROLE"), ("REPLICATION", "NOREPLICATION"),
                                         ("BYPASSRLS", "NOBYPASSRLS"), ("NOLOGIN", "LOGIN")))
def test_fixture_cluster_role_escalation_rejects_restore_and_is_reset(backup_runtime, grant, revoke):
    from test_model_secrets import fixture_codec
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    artifact = backup.create()  # Establishes the fixture's original safe role flags.
    try:
        with backup_runtime.admin() as connection:
            connection.execute("ALTER ROLE class_os_runtime " + grant)  # Closed constants, disposable fixture cluster only.
        with pytest.raises(BackupRejected):
            backup.check(artifact)
    finally:
        with backup_runtime.admin() as connection:
            connection.execute("ALTER ROLE class_os_runtime " + revoke)
    assert backup.check(artifact)["verified"] is True


@pytest.mark.db
def test_fixture_cluster_membership_escalation_rejects_restore_and_is_reset(backup_runtime):
    from test_model_secrets import fixture_codec
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    artifact = backup.create()
    try:
        with backup_runtime.admin() as connection:
            connection.execute("GRANT class_os_migrator TO class_os_runtime")
        with pytest.raises(BackupRejected):
            backup.check(artifact)
    finally:
        with backup_runtime.admin() as connection:
            connection.execute("REVOKE class_os_migrator FROM class_os_runtime")
    assert backup.check(artifact)["verified"] is True


@pytest.mark.db
def test_source_widened_acl_rejects_new_dump_without_repair_or_overwriting_backup(backup_runtime, monkeypatch):
    from test_model_secrets import fixture_codec
    backup = SyntheticBackup(backup_runtime, codec=fixture_codec)
    artifact = backup.create()
    path = backup_runtime.root / "backups" / (str(artifact) + ".dpapi")
    sealed = path.read_bytes()
    source = backup_runtime.database("migrator")
    def forbidden(*args, **kwargs):
        pytest.fail("Dump entered before source role guards")
    monkeypatch.setattr(backup, "_pg", forbidden)
    try:
        with source.transaction() as connection:
            connection.exec_driver_sql("GRANT SELECT(owner_id) ON class_os.owner_account TO class_os_runtime")
        with pytest.raises(BackupRejected):
            backup.create()
        assert list(path.parent.iterdir()) == [path] and path.read_bytes() == sealed
    finally:
        with source.transaction() as connection:
            connection.exec_driver_sql("REVOKE SELECT(owner_id) ON class_os.owner_account FROM class_os_runtime")
        source.close()


@pytest.mark.db
def test_valid_role_guards_only_read_metadata_not_business_rows(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)
    runtime = Database(database_urls["runtime"])
    statements = []
    def observed(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    try:
        with runtime.transaction(read_only=True) as connection:
            event.listen(runtime.engine, "before_cursor_execute", observed)
            try:
                validate_role_guards(connection)
            finally:
                event.remove(runtime.engine, "before_cursor_execute", observed)
        assert statements and all(statement.lstrip().startswith("SELECT") for statement in statements)
        assert not any("FROM class_os." in statement for statement in statements)
    finally:
        runtime.close()
        owner.close()


@pytest.mark.db
async def test_readiness_rejects_widened_column_permission_and_never_repairs(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)
    class FixtureRuntime:
        def database(self, role):
            return Database(database_urls[role], identity=role == "identity")
    app = compose(Settings(), FixtureRuntime())
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
            assert (await client.get("/health/ready")).status_code == 200
            with owner.transaction() as connection:
                connection.exec_driver_sql("GRANT SELECT(owner_id) ON class_os.owner_account TO class_os_runtime")
            response = await client.get("/health/ready")
            assert response.status_code == 503
            assert "owner_account" not in response.text and "class_os_runtime" not in response.text
            with owner.transaction(read_only=True) as connection:
                assert connection.execute(text("SELECT has_column_privilege('class_os_runtime','class_os.owner_account','owner_id','SELECT')")).scalar_one() is True
            with owner.transaction() as connection:
                connection.exec_driver_sql("REVOKE SELECT(owner_id) ON class_os.owner_account FROM class_os_runtime")
            assert (await client.get("/health/ready")).status_code == 200
    finally:
        owner.close()


@pytest.mark.db
def test_shadowed_privilege_function_cannot_hide_granted_audit_digest(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)
    try:
        with owner.transaction() as connection:
            connection.exec_driver_sql("GRANT SELECT(session_digest) ON class_os.business_audit TO class_os_runtime")
            connection.exec_driver_sql("""CREATE FUNCTION class_os.has_column_privilege(name,text,text,text)
                RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT false'""")
        with owner.transaction(read_only=True) as connection:
            with pytest.raises(RuntimeError, match="Database role safety guards failed"):
                validate_role_guards(connection)
    finally:
        owner.close()


@pytest.mark.db
@pytest.mark.parametrize("shadow_value,revoke,expected", (("false", False, 200), ("true", True, 503)))
async def test_readiness_uses_builtin_feature_permissions_not_shadowed_function(database_urls, shadow_value, revoke, expected):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)
    class FixtureRuntime:
        def database(self, role):
            return Database(database_urls[role], identity=role == "identity")
    try:
        with owner.transaction() as connection:
            connection.exec_driver_sql("CREATE FUNCTION class_os.has_column_privilege(name,text,text,text) "
                                       "RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT " + shadow_value + "'")
            if revoke:
                connection.exec_driver_sql("REVOKE UPDATE(name) ON class_os.student FROM class_os_runtime")
        app = compose(Settings(), FixtureRuntime())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
            assert (await client.get("/health/ready")).status_code == expected
    finally:
        owner.close()
