"""Read-only PostgreSQL relation surface, not a complete lifecycle inventory."""
from sqlalchemy import text


REGISTERED_TABLES = frozenset({"alembic_version", "database_state", "workspace", "owner_account", "bootstrap_capability",
                             "auth_session", "recovery_code", "identity_rate_limit", "identity_audit", "academic_term", "school_class",
                             "student", "enrollment", "command_proposal", "approval_receipt", "command_receipt", "business_audit",
                             "student_identifier", "record_revision", "manual_task", "export_job", "model_configuration"})


def relation_surface(connection):
    return tuple(dict(row) for row in connection.execute(text("""SELECT n.nspname AS namespace,c.relname AS name,
        CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'partitioned_table' WHEN 'v' THEN 'view'
             WHEN 'm' THEN 'materialized_view' WHEN 'f' THEN 'foreign_table' WHEN 'S' THEN 'sequence' END AS kind,
        c.relpersistence AS persistence,pg_get_userbyid(c.relowner) AS owner
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE LEFT(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema'
        AND c.relkind IN ('r','p','v','m','f','S') ORDER BY n.nspname,c.relname""")).mappings())


def validate_surface(connection, *, complete=False):
    relations = relation_surface(connection)
    if any(row["namespace"] != "class_os" or row["name"] not in REGISTERED_TABLES or row["kind"] != "table"
           or row["persistence"] != "p" or row["owner"] != "class_os_migrator" for row in relations):
        raise RuntimeError("Unregistered database objects")
    names = {row["name"] for row in relations}
    if complete and names != REGISTERED_TABLES:
        raise RuntimeError("Database relation surface incomplete")
    return names
