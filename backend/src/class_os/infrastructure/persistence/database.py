"""Synthetic PostgreSQL connection/UoW; migrations are never an HTTP operation."""
from contextlib import contextmanager
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from .schema_inventory import validate_surface


# New development migrations must never silently change the frozen R1 default.
R1_MIGRATION_TARGET = "0016"


class Database:
    def __init__(self, url, *, migration=False, identity=False):
        try:
            parsed = make_url(url)
            if migration and identity:
                raise ValueError()
            role = "class_os_migrator" if migration else "class_os_identity" if identity else "class_os_runtime"
            if (parsed.drivername != "postgresql+psycopg" or parsed.host != "127.0.0.1"
                    or parsed.username != role or parsed.query
                    or not re.fullmatch(r"class_os_synthetic_[a-z0-9_]{1,40}", parsed.database or "")):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Invalid synthetic database configuration") from None
        self.migration = migration
        self.identity = identity
        self.engine = create_engine(parsed, poolclass=NullPool, hide_parameters=True, echo=False,
                                    connect_args={"connect_timeout": 3, "options":
                                                  "-c search_path=class_os,pg_catalog -c timezone=UTC -c statement_timeout=5000 -c lock_timeout=1000"})

    @contextmanager
    def transaction(self, *, read_only=False):
        with self.engine.begin() as connection:
            if not 180000 <= int(connection.exec_driver_sql("SHOW server_version_num").scalar_one()) < 190000:
                raise RuntimeError("Unsupported PostgreSQL major version")
            if read_only:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            yield connection

    def close(self):
        self.engine.dispose()

    @contextmanager
    def identity_lease(self):
        """Hold only the fixed revocation lock across separately committed work.

        NullPool closes the physical connection on every exit, including faults
        during unlock. A session lock must never return to a shared pool.
        """
        if not self.identity:
            raise PermissionError("Identity connection required")
        with self.engine.connect() as connection:
            if not 180000 <= int(connection.exec_driver_sql("SHOW server_version_num").scalar_one()) < 190000:
                raise RuntimeError("Unsupported PostgreSQL major version")
            connection.exec_driver_sql("SET lock_timeout = '5s'")
            connection.execute(text("SELECT pg_advisory_lock(607103018)"))
            connection.commit()
            try:
                yield connection
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(607103018)"))
                connection.commit()


def migrate(database: Database, *, connection=None):
    if not database.migration:
        raise PermissionError("Runtime database role cannot migrate")
    if connection is None:
        with database.transaction() as owned:
            return migrate(database, connection=owned)
    if not connection.execute(text("SELECT pg_try_advisory_xact_lock(607103003)")).scalar_one():
        raise RuntimeError("Migration already running")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[4] / "db/migrations"))
    config.attributes["connection"] = connection
    scripts = ScriptDirectory.from_config(config)
    objects = validate_surface(connection)
    if objects and "alembic_version" not in objects:
        raise RuntimeError("Unregistered database objects")
    schema_owner = connection.execute(text(
        "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='class_os'"
    )).scalar_one_or_none()
    if schema_owner not in (None, "class_os_migrator"):
        raise RuntimeError("Invalid migration schema owner")
    version_table = connection.execute(text("SELECT to_regclass('class_os.alembic_version')")).scalar_one()
    if version_table:
        revisions = connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalars().all()
        if len(revisions) != 1 or revisions[0] not in {
                item.revision for item in scripts.iterate_revisions(R1_MIGRATION_TARGET, "base")}:
            raise RuntimeError("Unknown database revision")
    connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS class_os AUTHORIZATION class_os_migrator")
    command.upgrade(config, R1_MIGRATION_TARGET)
    validate_surface(connection, complete=True)
