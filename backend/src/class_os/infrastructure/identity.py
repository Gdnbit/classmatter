"""Identity-only PostgreSQL adapter: no student/record/task access."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from class_os.domain.identity import Bootstrap, Owner, RecoveryCode, Session


class PostgresIdentityStore:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def atomic(self):
        with self.database.transaction() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
            connection.execute(text("SELECT pg_advisory_xact_lock(607103018)"))
            mode = connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one()
            if mode != "synthetic-only":
                raise RuntimeError("Identity runtime mode rejected")
            yield IdentityTransaction(connection, self)

    def audit(self, connection, action, outcome, now):
        return connection.execute(text("INSERT INTO class_os.identity_audit(event_id, action, outcome, occurred_at) VALUES(:id,:action,:outcome,:now) RETURNING event_id"),
                                  {"id": uuid4(), "action": action, "outcome": outcome, "now": now}).scalar_one()

    def logout_audit(self, connection, request_id, binding, now):
        return self.operation_audit(connection, "logout", request_id, binding, now)

    def operation_audit(self, connection, action, request_id, binding, now):
        return connection.execute(text("""INSERT INTO class_os.identity_audit
            (event_id,action,outcome,occurred_at,request_id,session_digest,client_digest,csrf_digest)
            VALUES(:id,:action,'allowed',:now,:request_id,:session_digest,:client_digest,:csrf_digest) RETURNING event_id"""),
            {"id": uuid4(), "now": now, "request_id": request_id, "action": action, "session_digest": None, **binding}).scalar_one()

    @contextmanager
    def authorization_guard(self, callback):
        with self.database.identity_lease() as connection:
            with connection.begin():
                mode = connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one()
                if mode != "synthetic-only":
                    raise RuntimeError("Identity runtime mode rejected")
                result = callback(IdentityTransaction(connection, self))
            # Authorization and its audit are durable before business work.
            # The session-level lock survives this commit until the caller exits.
            yield result


class IdentityTransaction:
    def __init__(self, connection, store):
        self._connection = connection
        self._store = store

    def _mutate(self, statement, values=None, *, expected=1):
        result = self._connection.execute(statement, values)
        if result.rowcount != expected:
            raise RuntimeError("Missing durable identity mutation")

    def logout_receipt(self, request_id):
        return self.operation_receipt(request_id)

    def operation_receipt(self, request_id):
        row = self._connection.execute(text("""SELECT action,outcome,occurred_at,session_digest,client_digest,csrf_digest
            FROM class_os.identity_audit WHERE request_id=:id"""), {"id": request_id}).mappings().one_or_none()
        return dict(row) if row else None

    def logout_audit(self, request_id, binding, now):
        return self._store.logout_audit(self._connection, request_id, binding, now)

    def operation_audit(self, action, request_id, binding, now):
        return self._store.operation_audit(self._connection, action, request_id, binding, now)

    def logout_client_known(self, client_digest, csrf_digest, now):
        return self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.auth_session
            WHERE client_digest=:client AND csrf_digest=:csrf AND purpose='business'
            AND expires_at>:now AND last_seen_at>:idle)"""),
            {"client": client_digest, "csrf": csrf_digest, "now": now, "idle": now - timedelta(minutes=15)}).scalar_one()

    def owner(self):
        row = self._connection.execute(text("SELECT owner_id, workspace_id, password_hash, credential_version FROM class_os.owner_account")).mappings().one_or_none()
        return Owner(**row) if row else None

    def create_owner(self, owner, now):
        self._mutate(text("INSERT INTO class_os.workspace(workspace_id, created_at) VALUES(:id,:now)"), {"id": owner.workspace_id, "now": now})
        self._mutate(text("INSERT INTO class_os.owner_account(owner_id, workspace_id, password_hash, credential_version) VALUES(:owner_id,:workspace_id,:password_hash,:credential_version)"), asdict(owner))

    def update_owner(self, owner):
        self._mutate(text("UPDATE class_os.owner_account SET password_hash=:password_hash, credential_version=:credential_version WHERE owner_id=:owner_id AND workspace_id=:workspace_id"), asdict(owner))

    def bootstrap(self):
        row = self._connection.execute(text("SELECT secret_hash, expires_at, consumed_at FROM class_os.bootstrap_capability WHERE singleton=true")).mappings().one_or_none()
        return Bootstrap(**row) if row else None

    def save_bootstrap(self, bootstrap):
        self._mutate(text("INSERT INTO class_os.bootstrap_capability(singleton,secret_hash,expires_at,consumed_at) VALUES(true,:secret_hash,:expires_at,:consumed_at) ON CONFLICT(singleton) DO UPDATE SET secret_hash=EXCLUDED.secret_hash, expires_at=EXCLUDED.expires_at, consumed_at=EXCLUDED.consumed_at"), asdict(bootstrap))

    def session(self, token_digest):
        row = self._connection.execute(text("SELECT token_digest,owner_id,client_digest,csrf_digest,credential_version,purpose,expires_at,last_seen_at,reauthenticated_at,revoked_at FROM class_os.auth_session WHERE token_digest=:digest"), {"digest": token_digest}).mappings().one_or_none()
        return Session(**row) if row else None

    def save_session(self, session):
        self._mutate(text("INSERT INTO class_os.auth_session(token_digest,owner_id,client_digest,csrf_digest,credential_version,purpose,expires_at,last_seen_at,reauthenticated_at,revoked_at) VALUES(:token_digest,:owner_id,:client_digest,:csrf_digest,:credential_version,:purpose,:expires_at,:last_seen_at,:reauthenticated_at,:revoked_at) ON CONFLICT(token_digest) DO UPDATE SET last_seen_at=EXCLUDED.last_seen_at, reauthenticated_at=EXCLUDED.reauthenticated_at, revoked_at=EXCLUDED.revoked_at"), asdict(session))

    def revoke_sessions(self, now):
        # The existing identity advisory lock covers both count and mutation.
        expected = self._connection.execute(text("SELECT count(*) FROM class_os.auth_session WHERE revoked_at IS NULL")).scalar_one()
        self._mutate(text("UPDATE class_os.auth_session SET revoked_at=:now WHERE revoked_at IS NULL"), {"now": now}, expected=expected)

    def recovery(self, code_id):
        row = self._connection.execute(text("SELECT code_id,owner_id,code_hash,credential_version,consumed_at FROM class_os.recovery_code WHERE code_id=:id"), {"id": code_id}).mappings().one_or_none()
        return RecoveryCode(**row) if row else None

    def replace_codes(self, codes):
        expected = self._connection.execute(text("SELECT count(*) FROM class_os.recovery_code")).scalar_one()
        self._mutate(text("DELETE FROM class_os.recovery_code"), expected=expected)
        self._mutate(text("INSERT INTO class_os.recovery_code(code_id,owner_id,code_hash,credential_version,consumed_at) VALUES(:code_id,:owner_id,:code_hash,:credential_version,:consumed_at)"), [asdict(code) for code in codes], expected=len(codes))

    def consume_code(self, code_id, now):
        self._mutate(text("UPDATE class_os.recovery_code SET consumed_at=:now WHERE code_id=:id AND consumed_at IS NULL"), {"id": code_id, "now": now})

    def attempt(self, action, now):
        row = self._connection.execute(text("SELECT attempts,window_start FROM class_os.identity_rate_limit WHERE action=:action"), {"action": action}).mappings().one_or_none()
        count = row["attempts"] if row and now < row["window_start"] + timedelta(minutes=1) else 0
        if count >= 6:
            return False
        start = row["window_start"] if count else now
        self._mutate(text("INSERT INTO class_os.identity_rate_limit(action,attempts,window_start) VALUES(:action,:count,:start) ON CONFLICT(action) DO UPDATE SET attempts=EXCLUDED.attempts, window_start=EXCLUDED.window_start"), {"action": action, "count": count + 1, "start": start})
        return True

    def audit(self, action, outcome, now):
        return self._store.audit(self._connection, action, outcome, now)
