"""Owned native first-run composition. No HTTP listener or Agent registration.

The trusted desktop owns the pipe. Human password/approval input uses the
original ISB and control BCG; no database reset, default password or migration.
"""
import secrets
import json
from uuid import uuid4

from pwdlib import PasswordHash
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.local_runtime import LocalRuntime, protect
from class_os.infrastructure.durable_local_runtime import _surface, open_services


class NativeSetup:
    def __init__(self, runtime, *, development=False):
        if type(runtime) is not LocalRuntime or runtime.profile != 'conversation-d1':
            raise ValueError('Owned D1 runtime required')
        self.runtime = runtime
        self.development = development is True
        self.services = self.login = self.proposal = self.operation_id = self.receipt = None
        self.client = secrets.token_urlsafe(32)
        self.commit_key = uuid4()

    def close(self):
        if self.services is not None:
            try:
                if self.login is not None:
                    self.services.identity.logout(self.login.token, self.client, self.login.csrf)
            finally:
                self.services.close()
                self.services = self.login = None

    def status(self):
        self.runtime.configuration()
        identity = self.runtime.database('identity')
        business = self.runtime.database('runtime')
        try:
            with business.transaction(read_only=True) as connection:
                _surface(connection)
                controls = connection.execute(text('SELECT count(*) FROM class_os.conversation_control')).scalar_one()
            with identity.transaction(read_only=True) as connection:
                owners = connection.execute(text('SELECT count(*) FROM class_os.owner_account')).scalar_one()
            if owners not in (0, 1) or controls not in (0, 1) or controls > owners:
                raise ValueError('Setup requires review')
            if controls:
                services = open_services(self.runtime)
                try:
                    services.readiness()
                finally:
                    services.close()
            return {'owner_present': bool(owners), 'ready': bool(controls)}
        finally:
            identity.close()
            business.close()

    def create_owner(self, password):
        if self.status()['owner_present']:
            raise ValueError('Owner already exists')
        database = self.runtime.database('identity')
        try:
            boundary = IdentityBoundary(PostgresIdentityStore(database), PasswordHash.recommended())
            session = boundary.bootstrap(boundary.arm_bootstrap(), password, self.client)
            try:
                return {'recovery_codes': list(session.recovery_codes)}
            finally:
                boundary.logout(session.token, self.client, session.csrf)
        finally:
            database.close()

    def preview_control(self, password):
        if self.proposal is not None or self.status()['ready']:
            raise ValueError('Control setup already prepared')
        self.services = open_services(self.runtime)
        try:
            self.login = self.services.identity.login(password, self.client)
            auth = (self.login.token, self.client, self.login.csrf, self.login.subject.workspace_id)
            self.proposal = self.services.worker.preview(*auth, InitializeConversationControl(uuid4()))
            self.operation_id = str(uuid4())
            return {'operation_id': self.operation_id, 'payload_hash': self.proposal.payload_hash,
                    'payload': self.proposal.command.canonical(), 'risk': 'X'}
        except Exception:
            self.close()
            raise

    def approve_control(self, operation_id, payload_hash, confirmed):
        if (confirmed is not True or self.proposal is None or operation_id != self.operation_id
                or payload_hash != self.proposal.payload_hash):
            raise ValueError('Exact human confirmation required')
        if self.receipt is None:
            auth = (self.login.token, self.client, self.login.csrf, self.login.subject.workspace_id)
            approval = self.services.worker.approve(*auth, self.proposal.proposal_id, self.proposal.payload_hash)
            self.receipt = self.services.worker.commit(*auth, self.proposal.proposal_id, self.commit_key, approval)
        self.services.readiness()
        return {'ready': True, 'receipt_id': str(self.receipt.receipt_id)}

    def handle(self, payload):
        if type(payload) is not dict:
            raise ValueError('Closed setup request required')
        operation = payload.get('operation')
        if payload == {'operation': 'status'}:
            return self.status()
        if payload == {'operation': 'development_access'}:
            return self.development_access()
        if operation in ('create_owner', 'preview_control') and set(payload) == {'operation', 'password'}:
            password = payload['password']
            if type(password) is not str or not 16 <= len(password) <= 256:
                raise ValueError('Password policy required')
            return self.create_owner(password) if operation == 'create_owner' else self.preview_control(password)
        if operation == 'approve_control' and set(payload) == {'operation', 'operation_id', 'payload_hash', 'confirmed'}:
            return self.approve_control(payload['operation_id'], payload['payload_hash'], payload['confirmed'])
        raise ValueError('Unregistered setup request')

    def development_access(self):
        # Explicit trusted desktop flag only; never registered in HTTP/tools.
        # Refuse to adopt an existing personal Owner. No shared/default password.
        if not self.development:
            raise ValueError('Explicit local development required')
        state = self.status()
        marker = self.runtime.root / 'developer-identity.dpapi'
        if marker.exists():
            if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 8192:
                raise ValueError('Developer identity requires review')
            credentials = json.loads(protect(marker.read_bytes(), decrypt=True))
            if set(credentials) != {'schema_version', 'password'} or credentials['schema_version'] != 1:
                raise ValueError('Developer identity requires review')
            password = credentials['password']
        else:
            if state['owner_present']:
                raise ValueError('Existing personal identity cannot be adopted')
            password = secrets.token_urlsafe(48)
            payload = json.dumps({'schema_version': 1, 'password': password}).encode('utf-8')
            with marker.open('xb') as target:
                target.write(protect(payload))
        if not state['owner_present']:
            self.create_owner(password)  # Original ISB; synthetic developer only.
        if not state['ready']:
            proposal = self.preview_control(password)
            # Startup flag is the operator's explicit synthetic setup authorization.
            # This does not create any student/fact/task or promote a release Gate.
            self.approve_control(proposal['operation_id'], proposal['payload_hash'], True)
            self.close()
        services = open_services(self.runtime)
        try:
            services.readiness()
            result = services.identity.login(password, self.client)
            # Parent process only; set the original HttpOnly cookies before loading
            # the business UI. Neither password nor tokens enter renderer JS.
            return {'cookies': {'client': self.client, 'session': result.token, 'csrf': result.csrf}}
        finally:
            services.close()
