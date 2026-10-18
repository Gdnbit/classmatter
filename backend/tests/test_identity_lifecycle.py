import pytest

from class_os.application.identity import IdentityDenied
from test_identity import identity, setup, PASSWORD, CLIENT


OTHER_CLIENT = "synthetic-other-client-" + "b" * 32


@pytest.mark.db
def test_logout_all_revokes_all_devices_but_not_password_or_unused_recovery(identity):
    boundary, _, _ = identity
    first = setup(boundary)
    other = boundary.login(PASSWORD, OTHER_CLIENT)
    boundary.logout_all(first.token, CLIENT, first.csrf, PASSWORD)
    for session, client in ((first, CLIENT), (other, OTHER_CLIENT)):
        with pytest.raises(IdentityDenied):
            boundary.authenticate(session.token, client, session.csrf)
    assert boundary.login(PASSWORD, CLIENT).subject.owner_id == first.subject.owner_id
    assert boundary.exchange_recovery(first.recovery_codes[0], CLIENT).subject.owner_id == first.subject.owner_id


@pytest.mark.db
def test_reissue_kit_rotates_current_session_revokes_old_codes_and_devices(identity):
    boundary, _, _ = identity
    first = setup(boundary)
    other = boundary.login(PASSWORD, OTHER_CLIENT)
    renewed = boundary.reissue_recovery(first.token, CLIENT, first.csrf, PASSWORD)
    assert len(renewed.recovery_codes) == 5 and renewed.token != first.token
    assert boundary.authenticate(renewed.token, CLIENT, renewed.csrf).owner_id == first.subject.owner_id
    for session, client in ((first, CLIENT), (other, OTHER_CLIENT)):
        with pytest.raises(IdentityDenied):
            boundary.authenticate(session.token, client, session.csrf)
    with pytest.raises(IdentityDenied):
        boundary.exchange_recovery(first.recovery_codes[0], CLIENT)
    assert boundary.exchange_recovery(renewed.recovery_codes[0], CLIENT).subject.owner_id == first.subject.owner_id


@pytest.mark.db
def test_identity_lifecycle_requires_password_and_atomic_audit(identity, monkeypatch):
    boundary, _, _ = identity
    auth = setup(boundary)
    for action in (boundary.logout_all, boundary.reissue_recovery):
        with pytest.raises(IdentityDenied):
            action(auth.token, CLIENT, auth.csrf, "wrong-synthetic-password")
    original = boundary.store.audit
    monkeypatch.setattr(boundary.store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("injected")))
    with pytest.raises(RuntimeError):
        boundary.reissue_recovery(auth.token, CLIENT, auth.csrf, PASSWORD)
    with pytest.raises(RuntimeError):
        boundary.logout_all(auth.token, CLIENT, auth.csrf, PASSWORD)
    monkeypatch.setattr(boundary.store, "audit", original)
    assert boundary.authenticate(auth.token, CLIENT, auth.csrf).owner_id == auth.subject.owner_id
    assert boundary.exchange_recovery(auth.recovery_codes[0], CLIENT).subject.owner_id == auth.subject.owner_id
