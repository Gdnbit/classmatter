"""Password-free identity for the explicitly selected native development host.

Workspace/command bindings remain ISB-owned. Connection identifiers are not user
credentials and have no idle/login lifetime. The ordinary ISB is unchanged.
"""
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
import hmac
import secrets

from .identity import IdentityBoundary, IdentityDenied, digest
from class_os.domain.identity import IdentityResult, Owner, Session, Subject


DISABLED_PASSWORD = "!classmatter-local-no-password"
CONNECTION_END = datetime(9999, 1, 1, tzinfo=timezone.utc)


class NoPasswords:
    def hash(self, value):
        raise IdentityDenied()

    def verify(self, value, stored):
        return False


class LocalIdentityBoundary(IdentityBoundary):
    def __init__(self, store, owner_id, workspace_id, *, clock=lambda: datetime.now(timezone.utc)):
        self.store, self.clock = store, clock
        self.owner_id, self.workspace_id = owner_id, workspace_id
        self.hasher, self._dummy_hash = NoPasswords(), DISABLED_PASSWORD
        self._operation_context = ContextVar("classmatter_local_connection", default=None)

    def connect(self, client, *, previous_hash=None):
        """Trusted native pipe only; never registered as an HTTP or Agent tool."""
        def connect(tx, now):
            self._client(client)
            owner = tx.owner()
            if owner is None:
                owner = Owner(self.owner_id, self.workspace_id, DISABLED_PASSWORD)
                tx.create_owner(owner, now)
            elif (owner.owner_id, owner.workspace_id) != (self.owner_id, self.workspace_id):
                raise IdentityDenied()
            elif owner.password_hash != DISABLED_PASSWORD:
                if previous_hash is None or not hmac.compare_digest(owner.password_hash, previous_hash):
                    raise IdentityDenied()
                owner = replace(owner, password_hash=DISABLED_PASSWORD, credential_version=owner.credential_version + 1)
                tx.update_owner(owner)
                tx.revoke_sessions(now)
                tx.replace_codes(())
            return self._session(tx, owner, client, now)
        return self._run("session", connect)

    def _session(self, tx, owner, client, now, *, purpose="business", codes=()):
        if purpose != "business" or codes:
            raise IdentityDenied()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session = Session(digest(token), owner.owner_id, self._client(client), digest(csrf),
            owner.credential_version, purpose, CONNECTION_END, now, now)
        tx.save_session(session)
        return IdentityResult(token, csrf, Subject(owner.owner_id, owner.workspace_id,
            session.token_digest, now, CONNECTION_END), ())

    def _authenticated(self, tx, token, client, csrf, now, *, purpose="business"):
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise IdentityDenied()
        owner, session = tx.owner(), tx.session(digest(token))
        if (owner is None or session is None or owner.password_hash != DISABLED_PASSWORD
                or (owner.owner_id, owner.workspace_id) != (self.owner_id, self.workspace_id)
                or session.owner_id != owner.owner_id or session.revoked_at is not None
                or purpose != "business" or session.purpose != purpose
                or session.credential_version != owner.credential_version
                or session.expires_at != CONNECTION_END
                or not hmac.compare_digest(session.client_digest, self._client(client))
                or (csrf is not None and (not isinstance(csrf, str) or len(csrf) > 128
                    or not hmac.compare_digest(session.csrf_digest, digest(csrf))))):
            raise IdentityDenied()
        # Presence in this local connection supplies the command confirmation
        # context; never prompt for a password or replay a business operation.
        return owner, replace(session, reauthenticated_at=now)
