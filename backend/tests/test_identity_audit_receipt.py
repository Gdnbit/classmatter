from datetime import timedelta

import pytest
from sqlalchemy import text
from class_os.application.audit import AuditUnavailable

from test_identity import identity, setup, CLIENT, PASSWORD


@pytest.mark.db
@pytest.mark.parametrize("operation", ["bootstrap", "login", "logout_all", "reissue", "guard"])
def test_suppressed_identity_audit_cannot_commit_or_release_authorization(identity, operation):
    boundary, owner, clock = identity
    original = None if operation == "bootstrap" else setup(boundary)
    bootstrap_secret = boundary.arm_bootstrap() if operation == "bootstrap" else None
    with owner.transaction() as connection:
        session_before = connection.execute(text("SELECT token_digest,revoked_at,last_seen_at FROM class_os.auth_session ORDER BY token_digest")).all()
        kit_before = connection.execute(text("SELECT code_id,code_hash FROM class_os.recovery_code ORDER BY code_id")).all()
        count_before = connection.execute(text("SELECT count(*) FROM class_os.identity_audit")).scalar_one()
        connection.execute(text("CREATE FUNCTION class_os.suppress_identity_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"))
        connection.execute(text("CREATE TRIGGER suppress_identity_audit BEFORE INSERT ON class_os.identity_audit FOR EACH ROW EXECUTE FUNCTION class_os.suppress_identity_audit()"))
    clock[0] += timedelta(seconds=1)
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        if operation == "bootstrap":
            boundary.bootstrap(bootstrap_secret, PASSWORD, CLIENT)
        elif operation == "login":
            boundary.login(PASSWORD, CLIENT)
        elif operation == "logout_all":
            boundary.logout_all(original.token, CLIENT, original.csrf, PASSWORD)
        elif operation == "reissue":
            boundary.reissue_recovery(original.token, CLIENT, original.csrf, PASSWORD)
        else:
            with boundary.authorized_session(original.token, CLIENT, original.subject.workspace_id, original.csrf):
                pytest.fail("Authorization escaped without a durable audit")
    with owner.transaction() as connection:
        assert connection.execute(text("SELECT token_digest,revoked_at,last_seen_at FROM class_os.auth_session ORDER BY token_digest")).all() == session_before
        assert connection.execute(text("SELECT code_id,code_hash FROM class_os.recovery_code ORDER BY code_id")).all() == kit_before
        assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit")).scalar_one() == count_before
        if operation == "bootstrap":
            assert connection.execute(text("SELECT count(*) FROM class_os.owner_account")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM class_os.workspace")).scalar_one() == 0
            assert connection.execute(text("SELECT consumed_at FROM class_os.bootstrap_capability")).scalar_one() is None
        connection.execute(text("DROP TRIGGER suppress_identity_audit ON class_os.identity_audit"))
        connection.execute(text("DROP FUNCTION class_os.suppress_identity_audit()"))
    if operation == "bootstrap":
        assert boundary.bootstrap(bootstrap_secret, PASSWORD, CLIENT).subject.owner_id
    else:
        assert boundary.authenticate(original.token, CLIENT, original.csrf).owner_id == original.subject.owner_id
