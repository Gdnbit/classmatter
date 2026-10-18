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
