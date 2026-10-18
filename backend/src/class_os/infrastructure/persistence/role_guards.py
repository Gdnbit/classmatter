"""Owned synthetic profile's read-only critical guards, not a full ACL matrix."""
from sqlalchemy import text

from .schema_inventory import REGISTERED_TABLES


ROLE_NAMES = ("class_os_migrator", "class_os_identity", "class_os_runtime")
PRIVATE_IDENTITY_TABLES = frozenset(("owner_account", "bootstrap_capability", "auth_session",
                                     "recovery_code", "identity_rate_limit", "identity_audit"))
BUSINESS_TABLES = REGISTERED_TABLES - PRIVATE_IDENTITY_TABLES - {"workspace", "database_state", "alembic_version"}


def validate_role_guards(connection):
    def reject():
        raise RuntimeError("Database role safety guards failed")

    roles = connection.execute(text("""SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolcanlogin
        FROM pg_catalog.pg_roles WHERE rolname=ANY(CAST(:roles AS pg_catalog.text[]))"""), {"roles": list(ROLE_NAMES)}).mappings().all()
    flags = ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")
    if (len(roles) != len(ROLE_NAMES) or {row["rolname"] for row in roles} != set(ROLE_NAMES)
            or any(row["rolcanlogin"] is not True or any(row[flag] is not False for flag in flags) for row in roles)):
        reject()
    if connection.execute(text("""SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
        WHERE member IN (SELECT oid FROM pg_catalog.pg_roles WHERE rolname=ANY(CAST(:roles AS pg_catalog.text[])))
           OR roleid IN (SELECT oid FROM pg_catalog.pg_roles WHERE rolname=ANY(CAST(:roles AS pg_catalog.text[]))))"""),
        {"roles": list(ROLE_NAMES)}).scalar_one():
        reject()

    for role, forbidden in (("class_os_runtime", PRIVATE_IDENTITY_TABLES), ("class_os_identity", BUSINESS_TABLES)):
        if connection.execute(text("""SELECT EXISTS(SELECT 1 FROM pg_catalog.unnest(CAST(:tables AS pg_catalog.text[])) t(name)
            CROSS JOIN pg_catalog.unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) p(privilege)
            WHERE pg_catalog.has_any_column_privilege(CAST(:role AS pg_catalog.name),'class_os.'||t.name,p.privilege))"""),
            {"role": role, "tables": sorted(forbidden)}).scalar_one():
            reject()

    if connection.execute(text("""SELECT EXISTS(SELECT 1
        FROM pg_catalog.unnest(ARRAY['class_os_runtime','class_os_identity']) r(name)
        CROSS JOIN pg_catalog.unnest(CAST(:tables AS pg_catalog.text[])) t(name)
        CROSS JOIN pg_catalog.unnest(ARRAY['DELETE','TRUNCATE','TRIGGER','REFERENCES']) p(privilege)
        WHERE NOT(r.name='class_os_identity' AND t.name='recovery_code' AND p.privilege='DELETE')
          AND CASE WHEN p.privilege='REFERENCES'
              THEN pg_catalog.has_any_column_privilege(CAST(r.name AS pg_catalog.name),'class_os.'||t.name,p.privilege)
              ELSE pg_catalog.has_table_privilege(CAST(r.name AS pg_catalog.name),'class_os.'||t.name,p.privilege) END)"""),
        {"tables": sorted(REGISTERED_TABLES)}).scalar_one():
        reject()

    if connection.execute(text("""SELECT EXISTS(SELECT 1 FROM pg_catalog.unnest(ARRAY['class_os_runtime','class_os_identity']) r(name)
        CROSS JOIN pg_catalog.unnest(ARRAY['class_os','public']) s(name)
        WHERE pg_catalog.has_schema_privilege(CAST(r.name AS pg_catalog.name),s.name,'CREATE')
           OR pg_catalog.has_database_privilege(CAST(r.name AS pg_catalog.name),pg_catalog.current_database(),'CREATE'))""")).scalar_one():
        reject()
    if connection.execute(text("""SELECT pg_catalog.has_column_privilege('class_os_runtime',
        'class_os.business_audit','session_digest','SELECT')""")).scalar_one():
        reject()
