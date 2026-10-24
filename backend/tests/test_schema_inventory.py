import pytest
from sqlalchemy import text

from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import REGISTERED_TABLES, relation_surface, validate_surface


@pytest.mark.db
@pytest.mark.parametrize("definition", ["CREATE VIEW class_os.unregistered AS SELECT 1 AS synthetic_value",
                                       "CREATE MATERIALIZED VIEW class_os.unregistered AS SELECT 1 AS synthetic_value",
                                       "CREATE TABLE public.unregistered (synthetic_value int)",
                                       "CREATE SEQUENCE class_os.unregistered"])
def test_migration_cannot_silently_adopt_unregistered_relational_stores(database_urls, definition):
    database = Database(database_urls["migrator"], migration=True)
    try:
        migrate(database)
        with database.transaction() as connection:
            connection.execute(text(definition))
        with pytest.raises(RuntimeError, match="Unregistered database objects"):
            migrate(database)
        with database.transaction(read_only=True) as connection:
            name = "public.unregistered" if "public." in definition else "class_os.unregistered"
            assert connection.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar_one() is not None
    finally:
        database.close()


@pytest.mark.db
def test_readonly_relation_surface_is_complete_stable_and_contains_no_customer_rows(database_urls):
    database = Database(database_urls["migrator"], migration=True)
    try:
        migrate(database)
        with database.transaction(read_only=True) as connection:
            first = relation_surface(connection)
            assert validate_surface(connection, complete=True) == REGISTERED_TABLES
            assert relation_surface(connection) == first
            assert len(first) == 22
            assert all(set(row) == {"namespace", "name", "kind", "persistence", "owner"} for row in first)
    finally:
        database.close()


@pytest.mark.db
@pytest.mark.parametrize("definition,message", [("DROP TABLE class_os.manual_task", "Database relation surface incomplete"),
                                               ("ALTER TABLE class_os.manual_task SET UNLOGGED", "Unregistered database objects")])
def test_missing_or_unlogged_registered_store_is_not_healthy_migration(database_urls, definition, message):
    database = Database(database_urls["migrator"], migration=True)
    try:
        migrate(database)
        with database.transaction() as connection:
            connection.execute(text(definition))
        with pytest.raises(RuntimeError, match=message):
            migrate(database)
    finally:
        database.close()


@pytest.mark.db
def test_default_migration_targets_frozen_r1_and_rejects_even_a_known_future_revision(database_urls, monkeypatch):
    from types import SimpleNamespace
    from class_os.infrastructure.persistence import database as module

    owner = Database(database_urls["migrator"], migration=True)
    targets = []
    upgrade = module.command.upgrade

    def fixed_upgrade(config, target):
        targets.append(target)
        return upgrade(config, target)

    monkeypatch.setattr(module.command, "upgrade", fixed_upgrade)
    try:
        migrate(owner)
        migrate(owner)
        assert targets == ["0016", "0016"]
        with owner.transaction() as connection:
            connection.execute(text("UPDATE class_os.alembic_version SET version_num='future_test'"))
        original = module.ScriptDirectory.from_config

        def scripts_with_future_head(config):
            scripts = original(config)
            # A future script existing on disk must not admit its schema into
            # default R1. Only ancestors of the explicit R1 target are allowed.
            walk = scripts.walk_revisions
            scripts.walk_revisions = lambda *a, **kw: iter([SimpleNamespace(revision="future_test"), *walk(*a, **kw)])
            return scripts

        monkeypatch.setattr(module.ScriptDirectory, "from_config", scripts_with_future_head)
        with pytest.raises(RuntimeError, match="Unknown database revision"):
            migrate(owner)
        assert targets == ["0016", "0016"]
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "future_test"
            assert validate_surface(connection, complete=True) == REGISTERED_TABLES
    finally:
        owner.close()
