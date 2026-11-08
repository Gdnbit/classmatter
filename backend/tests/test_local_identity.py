"""No user credentials or time-based login lifecycle in local development."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.identity import IdentityDenied
from class_os.application.local_identity import LocalIdentityBoundary, DISABLED_PASSWORD
from test_identity import identity, setup, CLIENT, PASSWORD


@pytest.mark.db
def test_local_connection_has_no_password_and_does_not_expire(identity):
    ordinary, database, clock = identity
    local = LocalIdentityBoundary(ordinary.store, uuid4(), uuid4(), clock=lambda: clock[0])
    connection = local.connect(CLIENT)
    assert connection.recovery_codes == ()
    with database.transaction(read_only=True) as sql:
        assert sql.execute(text('SELECT password_hash FROM class_os.owner_account')).scalar_one() == DISABLED_PASSWORD
        assert sql.execute(text('SELECT count(*) FROM class_os.recovery_code')).scalar_one() == 0
    clock[0] += timedelta(days=730)
    subject = local.authorize(connection.token, CLIENT, connection.subject.workspace_id, connection.csrf)
    assert subject.reauthenticated_at == clock[0]
    with local.authorized_session(connection.token, CLIENT, subject.workspace_id, connection.csrf) as current:
        assert current.owner_id == subject.owner_id
    with pytest.raises(IdentityDenied):
        local.login(PASSWORD, CLIENT)
    with pytest.raises(IdentityDenied):
        ordinary.authenticate(connection.token, CLIENT, connection.csrf)


@pytest.mark.db
def test_conversion_preserves_workspace_revokes_legacy_and_rejects_wrong_binding(identity):
    ordinary, database, clock = identity
    previous = setup(ordinary)
    local = LocalIdentityBoundary(ordinary.store, previous.subject.owner_id,
        previous.subject.workspace_id, clock=lambda: clock[0])
    with pytest.raises(IdentityDenied):
        local.connect(CLIENT)
    with database.transaction(read_only=True) as sql:
        old_hash = sql.execute(text('SELECT password_hash FROM class_os.owner_account')).scalar_one()
    connection = local.connect(CLIENT, previous_hash=old_hash)
    assert connection.subject.owner_id == previous.subject.owner_id
    assert connection.subject.workspace_id == previous.subject.workspace_id
    with pytest.raises(IdentityDenied):
        ordinary.authenticate(previous.token, CLIENT, previous.csrf)
    with pytest.raises(IdentityDenied):
        local.authenticate(connection.token, CLIENT + 'x', connection.csrf)
    with pytest.raises(IdentityDenied):
        local.authorize(connection.token, CLIENT, uuid4(), connection.csrf)
    with pytest.raises(IdentityDenied):
        local.authenticate(connection.token, CLIENT, 'wrong')
    local.logout(connection.token, CLIENT, connection.csrf)
    with pytest.raises(IdentityDenied):
        local.authenticate(connection.token, CLIENT, connection.csrf)
    restarted = LocalIdentityBoundary(ordinary.store, previous.subject.owner_id,
        previous.subject.workspace_id, clock=lambda: clock[0])
    assert restarted.connect(CLIENT).subject.workspace_id == previous.subject.workspace_id
