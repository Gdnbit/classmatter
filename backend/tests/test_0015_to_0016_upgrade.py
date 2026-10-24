"""Nonempty 0015 -> 0016 forward upgrade; no historical migration edits."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pwdlib import PasswordHash
import pytest
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.application.roster import BusinessGateway, QueryGateway, CommandRejected
from class_os.domain.activity import CreateTask
from class_os.domain.roster import ChangeClass, ChangeTerm
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.roster import PostgresBusinessStore, BusinessTransaction
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import REGISTERED_TABLES
from test_activity_gateway import seed, submit
from test_identity import setup, CLIENT


class Legacy0015Transaction(BusinessTransaction):
    """Test-only old boundary, usable exclusively while constructing 0015 rows."""

    def authorize_boundary(self, binding, action, proposal_id):
        assert self._store.database.profile == "r1"
        assert self._connection.execute(text(
            "SELECT version_num FROM class_os.alembic_version"
        )).scalar_one() == "0015"


class Legacy0015Store(PostgresBusinessStore):
    def _transaction(self, connection):
        return Legacy0015Transaction(connection, self)


def snapshot(owner):
    # Test-owned, closed table registry only. No application read/export API.
    # Includes identity rows in memory to detect unintended migration mutation;
    # never writes them to logs, files or a release artifact.
    with owner.transaction(read_only=True) as connection:
        return {table: tuple(connection.execute(text(
            f"SELECT row_to_json(upgrade_snapshot_row.*)::text FROM class_os.{table} AS upgrade_snapshot_row ORDER BY row_to_json(upgrade_snapshot_row.*)::text"
        )).scalars()) for table in sorted(REGISTERED_TABLES - {"alembic_version"})}


def term_acl(owner):
    with owner.transaction(read_only=True) as connection:
        return dict(connection.execute(text("""SELECT attname,
            pg_catalog.has_column_privilege('class_os_runtime',attrelid,attnum,'UPDATE')
            FROM pg_catalog.pg_attribute WHERE attrelid='class_os.academic_term'::regclass
            AND attnum>0 AND NOT attisdropped ORDER BY attname""")).all())


@pytest.mark.db
def test_nonempty_0015_upgrade_preserves_rows_legacy_approval_and_exact_new_grants(database_urls):
    with ExitStack() as stack:
        owner = Database(database_urls["migrator"], migration=True)
        identity_database = Database(database_urls["identity"], identity=True)
        runtime_database = Database(database_urls["runtime"])
        for database in (owner, identity_database, runtime_database):
            stack.callback(database.close)
        with owner.transaction() as connection:
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "db/migrations"))
            config.attributes["connection"] = connection
            connection.exec_driver_sql("CREATE SCHEMA class_os AUTHORIZATION class_os_migrator")
            command.upgrade(config, "0015")
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0015"
        clock = [datetime(2026, 10, 8, 12, tzinfo=timezone.utc)]
        boundary = IdentityBoundary(PostgresIdentityStore(identity_database), PasswordHash.recommended(), clock=lambda: clock[0])
        auth = setup(boundary)
        credentials = (auth.token, CLIENT, auth.csrf, auth.subject.workspace_id)
        current = PostgresBusinessStore(runtime_database)
        with pytest.raises(CommandRejected):
            QueryGateway(boundary, current, clock=lambda: clock[0]).context(*credentials)
        store = Legacy0015Store(runtime_database)
        business = BusinessGateway(boundary, store, clock=lambda: clock[0])
        query = QueryGateway(boundary, store, clock=lambda: clock[0])
        classroom, student, record = seed((business, query, store, credentials, boundary, owner, clock))
        submit(business, credentials, record)
        submit(business, credentials, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
            "合成旧版本关联任务", student_id=student.student_id, source_record_id=record.record_id))
        legacy = business.preview(*credentials, ChangeClass("class.update", classroom.class_id, classroom.term_id, 1, "合成升级后班级"))
        approval = business.approve(*credentials, legacy.proposal_id, legacy.payload_hash)
        before, acl = snapshot(owner), term_acl(owner)
        assert all(not acl[column] for column in ("name", "start_date", "end_date"))
        migrate(owner)
        # All post-upgrade operations use the actual current production boundary.
        store = PostgresBusinessStore(runtime_database)
        business = BusinessGateway(boundary, store, clock=lambda: clock[0])
        query = QueryGateway(boundary, store, clock=lambda: clock[0])
        assert snapshot(owner) == before
        assert term_acl(owner) == {**acl, "name": True, "start_date": True, "end_date": True}
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0016"
            assert not connection.execute(text("SELECT pg_catalog.has_schema_privilege('class_os_runtime','class_os','CREATE')")).scalar_one()
        receipt = business.commit(*credentials, legacy.proposal_id, uuid4(), approval)
        assert receipt.resource_id == classroom.class_id and receipt.version == 2
        submit(business, credentials, ChangeTerm("term.update", classroom.class_id, classroom.term_id, 1,
            classroom.term_name, "合成升级学期", classroom.start_date, classroom.start_date - timedelta(days=1),
            classroom.end_date, classroom.end_date + timedelta(days=1)))
        after = snapshot(owner)
        for table in ("student", "enrollment", "record_revision", "manual_task"):
            assert after[table] == before[table]
        assert query.term_metadata(*credentials, classroom.class_id, classroom.term_id).version == 2
