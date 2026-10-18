from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from class_os.infrastructure.persistence.database import Database, migrate


@pytest.mark.parametrize("url", [
    "sqlite:///:memory:",
    "postgresql+psycopg://class_os_runtime@evil.example/class_os_synthetic_a",
    "postgresql+psycopg://class_os_runtime@127.0.0.1/real_school",
    "postgresql+psycopg://postgres@127.0.0.1/class_os_synthetic_a",
    "postgresql+psycopg://class_os_runtime@127.0.0.1/class_os_synthetic_a?host=evil.example",
])
def test_database_configuration_rejects_shared_or_unsafe_targets(url):
    with pytest.raises(ValueError, match="Invalid synthetic database configuration"):
        Database(url)


@pytest.mark.db
def test_empty_database_upgrade_and_idempotent_replay(database_urls):
    database = Database(database_urls["migrator"], migration=True)
    try:
        migrate(database)
        migrate(database)
        with database.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0016"
            assert connection.execute(text("SELECT data_mode FROM class_os.database_state")).scalar_one() == "synthetic-only"
            tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='class_os' ORDER BY tablename")).scalars().all()
            assert tables == ["academic_term", "alembic_version", "approval_receipt", "auth_session", "bootstrap_capability",
                              "business_audit", "command_proposal", "command_receipt", "database_state", "enrollment", "export_job", "identity_audit",
                              "identity_rate_limit", "manual_task", "model_configuration", "owner_account", "record_revision", "recovery_code", "school_class", "student", "student_identifier", "workspace"]
    finally:
        database.close()


@pytest.mark.db
def test_interrupted_migration_rolls_back_all_ddl_then_retries(database_urls):
    database = Database(database_urls["migrator"], migration=True)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            with database.transaction() as connection:
                migrate(database, connection=connection)
                raise RuntimeError("injected")
        with database.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT to_regclass('class_os.database_state')")).scalar_one() is None
        migrate(database)
    finally:
        database.close()


@pytest.mark.db
def test_runtime_role_cannot_migrate_create_or_change_runtime_mode(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    runtime = Database(database_urls["runtime"])
    try:
        migrate(owner)
        with pytest.raises(PermissionError):
            migrate(runtime)
        for statement in ("CREATE TABLE class_os.unauthorized (id int)",
                          "UPDATE class_os.database_state SET data_mode='approved-real-pilot'",
                          "UPDATE class_os.alembic_version SET version_num='unknown'"):
            with pytest.raises(DBAPIError):
                with runtime.transaction() as connection:
                    connection.execute(text(statement))
        with runtime.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT data_mode FROM class_os.database_state")).scalar_one() == "synthetic-only"
    finally:
        owner.close()
        runtime.close()


@pytest.mark.db
def test_unknown_revision_is_rejected_not_stamped_or_reset(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    try:
        migrate(owner)
        with owner.transaction() as connection:
            connection.execute(text("UPDATE class_os.alembic_version SET version_num='unknown'"))
        with pytest.raises(RuntimeError, match="Unknown database revision"):
            migrate(owner)
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "unknown"
    finally:
        owner.close()


@pytest.mark.db
def test_migration_lock_and_read_only_transaction(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    try:
        migrate(owner)
        with owner.transaction() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(607103003)"))
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(RuntimeError, match="Migration already running"):
                    pool.submit(migrate, owner).result(timeout=5)
        with pytest.raises(DBAPIError):
            with owner.transaction(read_only=True) as connection:
                connection.execute(text("UPDATE class_os.database_state SET data_mode='synthetic-only'"))
    finally:
        owner.close()


@pytest.mark.db
def test_unversioned_foreign_table_is_not_adopted(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    try:
        with owner.transaction() as connection:
            connection.execute(text("CREATE SCHEMA class_os"))
            connection.execute(text("CREATE TABLE class_os.unregistered (id int)"))
        with pytest.raises(RuntimeError, match="Unregistered database objects"):
            migrate(owner)
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT to_regclass('class_os.unregistered')")).scalar_one() is not None
            assert connection.execute(text("SELECT to_regclass('class_os.database_state')")).scalar_one() is None
    finally:
        owner.close()
