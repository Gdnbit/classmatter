"""Read-only PostgreSQL relation surface, not a complete lifecycle inventory."""
from sqlalchemy import text
from types import MappingProxyType


REGISTERED_TABLES = frozenset({"alembic_version", "database_state", "workspace", "owner_account", "bootstrap_capability",
                             "auth_session", "recovery_code", "identity_rate_limit", "identity_audit", "academic_term", "school_class",
                             "student", "enrollment", "command_proposal", "approval_receipt", "command_receipt", "business_audit",
                             "student_identifier", "record_revision", "manual_task", "export_job", "model_configuration"})

D1_TABLES = frozenset({"conversation_thread", "conversation_turn", "conversation_message", "conversation_run", "conversation_control"})
D1_COLUMNS = MappingProxyType({
    "conversation_control": frozenset({"workspace_id", "owner_id", "authority_id", "epoch", "head_hash", "created_at", "updated_at"}),
    "conversation_thread": frozenset({"workspace_id", "thread_id", "owner_id", "class_id", "term_id", "student_id",
        "enrollment_id", "title", "status", "version", "created_at", "updated_at", "cleared_at"}),
    "conversation_turn": frozenset({"workspace_id", "thread_id", "turn_id", "ordinal", "client_request_id", "request_hash",
        "mode", "draft_kind", "created_at"}),
    "conversation_message": frozenset({"workspace_id", "thread_id", "turn_id", "message_id", "role", "origin",
        "visibility", "body", "created_at"}),
    "conversation_run": frozenset({"workspace_id", "thread_id", "turn_id", "run_id", "state", "version", "created_at",
        "queued_until", "generation", "started_at", "lease_until", "ended_at", "cancel_requested_at",
        "input_tokens", "output_tokens", "duration_ms"}),
})
SCHEMA_PROFILES = MappingProxyType({"r1": ("0016", REGISTERED_TABLES),
                                   "conversation-d1": ("0018", REGISTERED_TABLES | D1_TABLES)})


def schema_profile(value="r1"):
    if type(value) is not str or value not in SCHEMA_PROFILES:
        raise ValueError("Unsupported synthetic schema profile")
    return SCHEMA_PROFILES[value]


def relation_surface(connection):
    return tuple(dict(row) for row in connection.execute(text("""SELECT n.nspname AS namespace,c.relname AS name,
        CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'partitioned_table' WHEN 'v' THEN 'view'
             WHEN 'm' THEN 'materialized_view' WHEN 'f' THEN 'foreign_table' WHEN 'S' THEN 'sequence' END AS kind,
        c.relpersistence AS persistence,pg_get_userbyid(c.relowner) AS owner
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE LEFT(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema'
        AND c.relkind IN ('r','p','v','m','f','S') ORDER BY n.nspname,c.relname""")).mappings())


def validate_surface(connection, *, complete=False, profile="r1"):
    _, registered = schema_profile(profile)
    relations = relation_surface(connection)
    if any(row["namespace"] != "class_os" or row["name"] not in registered or row["kind"] != "table"
           or row["persistence"] != "p" or row["owner"] != "class_os_migrator" for row in relations):
        raise RuntimeError("Unregistered database objects")
    names = {row["name"] for row in relations}
    if complete and names != registered:
        raise RuntimeError("Database relation surface incomplete")
    return names
