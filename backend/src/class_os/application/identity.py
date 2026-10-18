"""Single-owner Identity Security Boundary; never handles student business state."""
from dataclasses import replace
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from uuid import UUID, uuid4

from class_os.domain.identity import Bootstrap, IdentityResult, Owner, RecoveryCode, Session, Subject, IdentityOperation
from class_os.application.audit import require_audit


class IdentityDenied(Exception):
    def __init__(self):
        super().__init__("Identity request rejected")


class IdentityAlreadyCommitted(Exception):
    def __init__(self):
        super().__init__("Identity operation already committed; secret output is not replayable")


OPERATION_ACTIONS = frozenset(("bootstrap", "login", "reauthenticate", "logout_all", "recovery_reissue", "recovery_exchange", "recovery_complete"))
PRE_SESSION_ACTIONS = frozenset(("bootstrap", "login", "recovery_exchange"))


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class IdentityBoundary:
    def __init__(self, store, password_hasher, *, clock=lambda: datetime.now(timezone.utc)):
        self.store = store
        self.hasher = password_hasher
        self.clock = clock
        self._dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))
        self._operation_context = ContextVar("class_os_identity_operation", default=None)

    @contextmanager
    def operation(self, action, request_id, client, csrf, token=None):
        context = IdentityOperation(request_id, action, client, csrf, token)
        marker = self._operation_context.set(context)
        try:
            yield
        finally:
            self._operation_context.reset(marker)

    def _run(self, action, callback, *, limited=False):
        result = None
        denied = duplicate = False
        with self.store.atomic() as tx:
            now = self._now()
            try:
                if limited and not tx.attempt(action, now):
                    raise IdentityDenied()
                operation = self._operation_context.get()
                binding = None
                if operation is not None:
                    if (type(operation.request_id) is not UUID or action not in OPERATION_ACTIONS or operation.action != action
                            or (action not in PRE_SESSION_ACTIONS and operation.token is None)
                            or (action in PRE_SESSION_ACTIONS and operation.token is not None)):
                        raise IdentityDenied()
                    binding = self._logout_binding(operation.client, operation.csrf, operation.token)
                    previous = tx.operation_receipt(operation.request_id)
                    if previous:
                        self._match_operation(previous, binding, now, action)
                        duplicate = True
                if not duplicate:
                    result = callback(tx, now)
                    if operation is not None:
                        require_audit(tx.operation_audit, action, operation.request_id, binding, now)
            except IdentityDenied:
                denied = True
            # Denials/attempt counters must commit too; audit failure rolls all back.
            require_audit(tx.audit, action, "denied" if denied or duplicate else "allowed", now)
        if denied:
            raise IdentityDenied()
        if duplicate:
            raise IdentityAlreadyCommitted()
        return result

    def operation_status(self, action, request_id, client, csrf):
        def status(tx, now):
            if action not in OPERATION_ACTIONS or type(request_id) is not UUID:
                raise IdentityDenied()
            binding = self._logout_binding(client, csrf)
            previous = tx.operation_receipt(request_id)
            if previous is None:
                raise IdentityDenied()
            self._match_operation(previous, binding, now, action)
            return "committed"
        return self._run("operation_status", status)

    def _now(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise RuntimeError("Identity clock must be UTC")
        return now

    @contextmanager
    def authorized_session(self, token, client, workspace_id, csrf):
        """Linearize QG/BCG operations with credential/session revocation."""
        def authorize(tx):
            now = self._now()
            subject, denied = None, False
            try:
                owner, session = self._authenticated(tx, token, client, csrf, now)
                if not csrf or str(owner.workspace_id) != str(workspace_id):
                    raise IdentityDenied()
                tx.save_session(replace(session, last_seen_at=now))
                subject = Subject(owner.owner_id, owner.workspace_id, session.token_digest, session.reauthenticated_at, session.expires_at)
            except IdentityDenied:
                denied = True
            require_audit(tx.audit, "session", "denied" if denied else "allowed", now)
            return subject, denied

        with self.store.authorization_guard(authorize) as (subject, denied):
            if denied:
                raise IdentityDenied()
            yield subject

    @staticmethod
    def _client(client):
        if not isinstance(client, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", client):
            raise IdentityDenied()
        return digest(client)

    @staticmethod
    def _password(password):
        if not isinstance(password, str) or not 16 <= len(password) <= 256:
            raise IdentityDenied()

    def arm_bootstrap(self):
        def arm(tx, now):
            if tx.owner() is not None:
                raise IdentityDenied()
            secret = secrets.token_urlsafe(32)
            tx.save_bootstrap(Bootstrap(self.hasher.hash(secret), now + timedelta(minutes=10)))
            return secret
        return self._run("bootstrap_arm", arm)

    def _kit(self, tx, owner):
        plain = []
        records = []
        for _ in range(5):
            code_id, value = uuid4(), secrets.token_urlsafe(24)
            plain.append(f"{code_id}.{value}")
            records.append(RecoveryCode(code_id, owner.owner_id, self.hasher.hash(value), owner.credential_version))
        tx.replace_codes(records)
        return tuple(plain)

    def _session(self, tx, owner, client, now, *, purpose="business", codes=()):
        client_digest = self._client(client)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session = Session(digest(token), owner.owner_id, client_digest, digest(csrf), owner.credential_version,
                          purpose, now + timedelta(minutes=10 if purpose == "recovery" else 60), now, now)
        tx.save_session(session)
        return IdentityResult(token, csrf, Subject(owner.owner_id, owner.workspace_id, session.token_digest, now, session.expires_at), codes)

    def bootstrap(self, secret, password, client):
        def create(tx, now):
            self._client(client)
            self._password(password)
            bootstrap = tx.bootstrap()
            if (tx.owner() is not None or bootstrap is None or bootstrap.consumed_at is not None
                    or now >= bootstrap.expires_at or not isinstance(secret, str) or len(secret) > 128
                    or not self.hasher.verify(secret, bootstrap.secret_hash)):
                raise IdentityDenied()
            owner = Owner(uuid4(), uuid4(), self.hasher.hash(password))
            tx.create_owner(owner, now)
            tx.save_bootstrap(replace(bootstrap, consumed_at=now))
            return self._session(tx, owner, client, now, codes=self._kit(tx, owner))
        return self._run("bootstrap", create, limited=True)

    def login(self, password, client):
        def login(tx, now):
            self._client(client)
            self._password(password)
            owner = tx.owner()
            valid = self.hasher.verify(password, owner.password_hash if owner else self._dummy_hash)
            if not owner or not valid:
                raise IdentityDenied()
            return self._session(tx, owner, client, now)
        return self._run("login", login, limited=True)

    def _authenticated(self, tx, token, client, csrf, now, *, purpose="business"):
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise IdentityDenied()
        session = tx.session(digest(token))
        owner = tx.owner()
        if (not session or not owner or session.owner_id != owner.owner_id or session.revoked_at is not None
                or session.purpose != purpose or session.credential_version != owner.credential_version
                or now >= session.expires_at or now >= session.last_seen_at + timedelta(minutes=15)
                or not hmac.compare_digest(session.client_digest, self._client(client))
                or (csrf is not None and (not isinstance(csrf, str) or len(csrf) > 128
                                         or not hmac.compare_digest(session.csrf_digest, digest(csrf))))):
            raise IdentityDenied()
        return owner, session

    def authenticate(self, token, client, csrf=None):
        def authenticate(tx, now):
            owner, session = self._authenticated(tx, token, client, csrf, now)
            tx.save_session(replace(session, last_seen_at=now))
            return Subject(owner.owner_id, owner.workspace_id, session.token_digest, session.reauthenticated_at, session.expires_at)
        return self._run("session", authenticate)

    def authorize(self, token, client, workspace_id, csrf=None):
        def authorize(tx, now):
            owner, session = self._authenticated(tx, token, client, csrf, now)
            if str(owner.workspace_id) != str(workspace_id):
                raise IdentityDenied()
            tx.save_session(replace(session, last_seen_at=now))
            return Subject(owner.owner_id, owner.workspace_id, session.token_digest, session.reauthenticated_at, session.expires_at)
        return self._run("session", authorize)

    def _logout_binding(self, client, csrf, token=None):
        if not isinstance(csrf, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", csrf):
            raise IdentityDenied()
        binding = {"client_digest": self._client(client), "csrf_digest": digest(csrf)}
        if token is not None:
            if not isinstance(token, str) or not 32 <= len(token) <= 128:
                raise IdentityDenied()
            binding["session_digest"] = digest(token)
        return binding

    @staticmethod
    def _match_logout(row, binding, now):
        IdentityBoundary._match_operation(row, binding, now, "logout")

    @staticmethod
    def _match_operation(row, binding, now, action):
        if (row["action"] != action or row["outcome"] != "allowed"
                or not row["occurred_at"] <= now < row["occurred_at"] + timedelta(minutes=10)
                or any(not hmac.compare_digest(row[key], value) for key, value in binding.items())):
            raise IdentityDenied()

    def logout(self, token, client, csrf, request_id=None):
        def logout(tx, now):
            if not csrf:
                raise IdentityDenied()
            if request_id is not None:
                if type(request_id) is not UUID:
                    raise IdentityDenied()
                binding = self._logout_binding(client, csrf, token)
                existing = tx.logout_receipt(request_id)
                if existing:
                    self._match_logout(existing, binding, now)
                    return  # Old result only; never revoke a new session.
            _, session = self._authenticated(tx, token, client, csrf, now)
            tx.save_session(replace(session, revoked_at=now))
            if request_id is not None:
                require_audit(tx.logout_audit, request_id, binding, now)
        return self._run("logout", logout)

    def logout_status(self, request_id, client, csrf):
        def status(tx, now):
            if type(request_id) is not UUID:
                raise IdentityDenied()
            binding = self._logout_binding(client, csrf)
            row = tx.logout_receipt(request_id)
            if row:
                self._match_logout(row, binding, now)
                return "committed"
            if not tx.logout_client_known(binding["client_digest"], binding["csrf_digest"], now):
                raise IdentityDenied()
            return "not_committed"
        # This never returns Subject, token, CSRF or recovery codes.
        return self._run("logout_status", status)

    def reauthenticate(self, token, client, csrf, password):
        def reauthenticate(tx, now):
            if not csrf:
                raise IdentityDenied()
            self._password(password)
            owner, session = self._authenticated(tx, token, client, csrf, now)
            if not self.hasher.verify(password, owner.password_hash):
                raise IdentityDenied()
            tx.save_session(replace(session, revoked_at=now))
            return self._session(tx, owner, client, now)
        return self._run("reauthenticate", reauthenticate, limited=True)

    def logout_all(self, token, client, csrf, password):
        def logout(tx, now):
            if not csrf:
                raise IdentityDenied()
            self._password(password)
            owner, _ = self._authenticated(tx, token, client, csrf, now)
            if not self.hasher.verify(password, owner.password_hash):
                raise IdentityDenied()
            tx.revoke_sessions(now)
        return self._run("logout_all", logout, limited=True)

    def reissue_recovery(self, token, client, csrf, password):
        def reissue(tx, now):
            if not csrf:
                raise IdentityDenied()
            self._password(password)
            owner, _ = self._authenticated(tx, token, client, csrf, now)
            if not self.hasher.verify(password, owner.password_hash):
                raise IdentityDenied()
            # New codes replace old hashes. All previous business/recovery
            # sessions are revoked; only this client's freshly issued session
            # remains. Plain codes exist only in this one response.
            codes = self._kit(tx, owner)
            tx.revoke_sessions(now)
            return self._session(tx, owner, client, now, codes=codes)
        return self._run("recovery_reissue", reissue, limited=True)

    def exchange_recovery(self, code, client):
        def exchange(tx, now):
            self._client(client)
            try:
                if not isinstance(code, str) or len(code) > 160:
                    raise ValueError()
                selector, secret = code.split(".", 1)
                code_id = UUID(selector)
            except (ValueError, TypeError):
                raise IdentityDenied() from None
            record, owner = tx.recovery(code_id), tx.owner()
            valid = self.hasher.verify(secret, record.code_hash if record else self._dummy_hash)
            if (not record or not owner or not valid or record.consumed_at is not None
                    or record.owner_id != owner.owner_id or record.credential_version != owner.credential_version):
                raise IdentityDenied()
            tx.consume_code(code_id, now)
            return self._session(tx, owner, client, now, purpose="recovery")
        return self._run("recovery_exchange", exchange, limited=True)

    def complete_recovery(self, token, client, csrf, new_password):
        def complete(tx, now):
            if not csrf:
                raise IdentityDenied()
            self._password(new_password)
            owner, _ = self._authenticated(tx, token, client, csrf, now, purpose="recovery")
            owner = replace(owner, password_hash=self.hasher.hash(new_password), credential_version=owner.credential_version + 1)
            tx.update_owner(owner)
            tx.revoke_sessions(now)
            return self._session(tx, owner, client, now, codes=self._kit(tx, owner))
        return self._run("recovery_complete", complete, limited=True)
