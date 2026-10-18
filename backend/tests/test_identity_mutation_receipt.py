"""Identity success requires actual writes, including bulk revoke/kit changes."""
from datetime import timedelta

import pytest
from sqlalchemy import text

from class_os.application.identity import IdentityDenied
from test_identity import identity, setup, CLIENT, PASSWORD


TABLES = ("workspace", "owner_account", "bootstrap_capability", "auth_session",
          "recovery_code", "identity_rate_limit", "identity_audit")
CASES = (
    ("arm", "bootstrap_capability", "INSERT"),
    ("bootstrap", "workspace", "INSERT"),
    ("bootstrap", "owner_account", "INSERT"),
    ("bootstrap", "bootstrap_capability", "UPDATE"),
    ("login", "auth_session", "INSERT"),
    ("login", "identity_rate_limit", "INSERT"),
    ("login-repeat", "identity_rate_limit", "UPDATE"),
    ("logout", "auth_session", "UPDATE"),
    ("logout-all", "auth_session", "UPDATE"),
    ("reauthenticate", "auth_session", "UPDATE"),
    ("exchange", "recovery_code", "UPDATE"),
    ("exchange", "auth_session", "INSERT"),
    ("complete", "owner_account", "UPDATE"),
    ("complete", "auth_session", "UPDATE"),
    ("complete", "recovery_code", "DELETE"),
    ("complete", "recovery_code", "INSERT"),
    ("reissue", "recovery_code", "DELETE"),
    ("reissue", "recovery_code", "INSERT"),
    ("reissue", "auth_session", "UPDATE"),
    ("guard", "auth_session", "UPDATE"),
)


def snapshot(owner):
    with owner.transaction(read_only=True) as connection:
        return {table: connection.execute(text(f"SELECT row_to_json(t)::text FROM class_os.{table} t ORDER BY row_to_json(t)::text")).scalars().all()
                for table in TABLES}


@pytest.mark.db
@pytest.mark.parametrize("operation,table,event", CASES)
def test_suppressed_identity_write_never_returns_success_or_commits_partial_state(identity, operation, table, event):
    boundary, owner, clock = identity
    original = None if operation in ("arm", "bootstrap") else setup(boundary)
    bootstrap = boundary.arm_bootstrap() if operation == "bootstrap" else None
    recovery = boundary.exchange_recovery(original.recovery_codes[0], CLIENT) if operation == "complete" else None
    if operation in ("logout-all", "login-repeat"):
        boundary.login(PASSWORD, CLIENT)
    clock[0] += timedelta(seconds=1)

    def execute():
        if operation == "arm":
            return boundary.arm_bootstrap()
        if operation == "bootstrap":
            return boundary.bootstrap(bootstrap, PASSWORD, CLIENT)
        if operation in ("login", "login-repeat"):
            return boundary.login(PASSWORD, CLIENT)
        if operation == "logout":
            return boundary.logout(original.token, CLIENT, original.csrf)
        if operation == "logout-all":
            return boundary.logout_all(original.token, CLIENT, original.csrf, PASSWORD)
        if operation == "reauthenticate":
            return boundary.reauthenticate(original.token, CLIENT, original.csrf, PASSWORD)
        if operation == "exchange":
            return boundary.exchange_recovery(original.recovery_codes[0], CLIENT)
        if operation == "complete":
            return boundary.complete_recovery(recovery.token, CLIENT, recovery.csrf, "new-synthetic-password-123")
        if operation == "reissue":
            return boundary.reissue_recovery(original.token, CLIENT, original.csrf, PASSWORD)
        with boundary.authorized_session(original.token, CLIENT, original.subject.workspace_id, original.csrf):
            return True

    before = snapshot(owner)
    with owner.transaction() as connection:
        connection.execute(text("CREATE FUNCTION class_os.suppress_identity_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"))
        connection.execute(text(f"CREATE TRIGGER suppress_identity_write BEFORE {event} ON class_os.{table} FOR EACH ROW EXECUTE FUNCTION class_os.suppress_identity_write()"))
    with pytest.raises(RuntimeError, match="Missing durable identity mutation"):
        execute()
    assert snapshot(owner) == before
    with owner.transaction() as connection:
        connection.execute(text(f"DROP TRIGGER suppress_identity_write ON class_os.{table}"))
        connection.execute(text("DROP FUNCTION class_os.suppress_identity_write()"))
    result = execute()
    if operation in ("logout", "logout-all", "reauthenticate", "reissue", "complete"):
        with pytest.raises(IdentityDenied):
            boundary.authenticate(original.token, CLIENT, original.csrf)
    if operation == "exchange":
        with pytest.raises(IdentityDenied):
            boundary.exchange_recovery(original.recovery_codes[0], CLIENT)
    if operation in ("bootstrap", "login", "login-repeat", "reauthenticate", "reissue", "complete"):
        assert boundary.authenticate(result.token, CLIENT, result.csrf).owner_id == result.subject.owner_id


@pytest.mark.db
@pytest.mark.parametrize("fault", ("partial-revoke", "partial-kit-delete", "partial-kit-insert"))
def test_identity_bulk_mutation_requires_every_expected_row(identity, fault):
    boundary, owner, _ = identity
    original = setup(boundary)
    boundary.login(PASSWORD, CLIENT)
    before = snapshot(owner)
    with owner.transaction() as connection:
        if fault == "partial-revoke":
            table, event = "auth_session", "UPDATE"
            selected = connection.execute(text("SELECT token_digest FROM class_os.auth_session ORDER BY token_digest LIMIT 1")).scalar_one()
            body = f"IF OLD.token_digest='{selected}' THEN RETURN NULL; END IF; RETURN NEW;"
        elif fault == "partial-kit-delete":
            table, event = "recovery_code", "DELETE"
            selected = connection.execute(text("SELECT code_id FROM class_os.recovery_code ORDER BY code_id LIMIT 1")).scalar_one()
            body = f"IF OLD.code_id='{selected}'::uuid THEN RETURN NULL; END IF; RETURN OLD;"
        else:
            table, event = "recovery_code", "INSERT"
            body = "IF (SELECT count(*) FROM class_os.recovery_code)>=2 THEN RETURN NULL; END IF; RETURN NEW;"
        # Only synthetic DB-generated UUID/digest is embedded in test fault SQL.
        connection.execute(text(f"CREATE FUNCTION class_os.partial_identity_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {body} END $$"))
        connection.execute(text(f"CREATE TRIGGER partial_identity_write BEFORE {event} ON class_os.{table} FOR EACH ROW EXECUTE FUNCTION class_os.partial_identity_write()"))
    with pytest.raises(RuntimeError, match="Missing durable identity mutation"):
        if fault == "partial-revoke":
            boundary.logout_all(original.token, CLIENT, original.csrf, PASSWORD)
        else:
            boundary.reissue_recovery(original.token, CLIENT, original.csrf, PASSWORD)
    assert snapshot(owner) == before
    with owner.transaction() as connection:
        connection.execute(text(f"DROP TRIGGER partial_identity_write ON class_os.{table}"))
        connection.execute(text("DROP FUNCTION class_os.partial_identity_write()"))
    assert boundary.authenticate(original.token, CLIENT, original.csrf).owner_id == original.subject.owner_id
