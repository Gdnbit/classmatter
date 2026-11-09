"""Owned native first-run composition. No HTTP listener or Agent registration.

The trusted desktop owns the pipe. Human password/approval input uses the
original ISB and control BCG; no database reset, default password or migration.
"""
import secrets
import json
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.local_runtime import LocalRuntime, protect
from class_os.infrastructure.durable_local_runtime import _surface, open_services


class NativeSetup:
    def __init__(self, runtime, *, development=False):
        if type(runtime) is not LocalRuntime or runtime.profile not in ('conversation-d1', 'workbench-d2', 'workspace-chat-d3', 'classroom-work-d4'):
            raise ValueError('Owned D1/D2 runtime required')
        if runtime.profile == 'workbench-d2':
            from .workbench_upgrade import verify_upgrade_receipt
            verify_upgrade_receipt(runtime)
        elif runtime.profile == 'workspace-chat-d3':
            from .workspace_upgrade import verify_upgrade_receipt
            verify_upgrade_receipt(runtime)
        elif runtime.profile == 'classroom-work-d4':
            from .classroom_upgrade import verify_upgrade_receipt
            verify_upgrade_receipt(runtime)
        self.runtime = runtime
        self.development = development is True
        self.services = self.login = self.proposal = self.operation_id = self.receipt = None
        self.client = secrets.token_urlsafe(32)
        self.commit_key = uuid4()

    def _open_services(self):
        if self.runtime.profile in ('workspace-chat-d3', 'classroom-work-d4'):
            from .workspace_local_runtime import open_services as open_workspace
            return open_workspace(self.runtime, local_development=self.development and (self.runtime.root / 'local-development.dpapi').exists())
        if self.runtime.profile == 'workbench-d2':
            from .workbench_local_runtime import open_services as open_workbench
            return open_workbench(self.runtime)
        return open_services(self.runtime)

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
                if self.runtime.profile in ('workspace-chat-d3', 'classroom-work-d4'):
                    from .workspace_local_runtime import surface
                    surface(connection, profile=self.runtime.profile)
                elif self.runtime.profile == 'workbench-d2':
                    from .workbench_local_runtime import surface
                    surface(connection)
                else:
                    _surface(connection)
                controls = connection.execute(text('SELECT count(*) FROM class_os.conversation_control')).scalar_one()
            with identity.transaction(read_only=True) as connection:
                owners = connection.execute(text('SELECT count(*) FROM class_os.owner_account')).scalar_one()
            if owners not in (0, 1) or controls not in (0, 1) or controls > owners:
                raise ValueError('Setup requires review')
            if self.runtime.profile in ('workbench-d2', 'workspace-chat-d3', 'classroom-work-d4') and (owners != 1 or controls != 1):
                raise ValueError('Existing D2 identity and control required; no bootstrap')
            if controls:
                services = self._open_services()
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
        self.services = self._open_services()
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
        if operation == 'development_reauthenticate' and set(payload) == {'operation', 'client', 'session', 'csrf'}:
            if any(type(payload[name]) is not str or not 32 <= len(payload[name]) <= 128 for name in ('client', 'session', 'csrf')):
                raise ValueError('Closed identity context required')
            return self.development_reauthenticate(payload['client'], payload['session'], payload['csrf'])
        if operation in ('create_owner', 'preview_control') and set(payload) == {'operation', 'password'}:
            password = payload['password']
            if type(password) is not str or not 16 <= len(password) <= 256:
                raise ValueError('Password policy required')
            return self.create_owner(password) if operation == 'create_owner' else self.preview_control(password)
        if operation == 'approve_control' and set(payload) == {'operation', 'operation_id', 'payload_hash', 'confirmed'}:
            return self.approve_control(payload['operation_id'], payload['payload_hash'], payload['confirmed'])
        raise ValueError('Unregistered setup request')

    def _developer_password(self):
        if not self.development:
            raise ValueError('Explicit local development required')
        marker = self.runtime.root / 'developer-identity.dpapi'
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 8192:
            raise ValueError('Developer identity requires review')
        credentials = json.loads(protect(marker.read_bytes(), decrypt=True))
        if (set(credentials) != {'schema_version', 'password'} or credentials['schema_version'] != 1
                or type(credentials['password']) is not str or not 16 <= len(credentials['password']) <= 256):
            raise ValueError('Developer identity requires review')
        return credentials['password']

    def development_reauthenticate(self, client, token, csrf):
        if not self.development:
            raise ValueError('Explicit local development required')
        if self.runtime.profile in ('workspace-chat-d3', 'classroom-work-d4'):
            return self.local_access()
        password = self._developer_password()
        services = self._open_services()
        try:
            services.readiness()
            result = services.identity.reauthenticate(token, client, csrf, password)
            return {'cookies': {'client': client, 'session': result.token, 'csrf': result.csrf}}
        finally:
            services.close()

    def development_access(self):
        if not self.development:
            raise ValueError('Explicit local development required')
        if self.runtime.profile in ('workspace-chat-d3', 'classroom-work-d4'):
            return self.local_access()
        # Explicit trusted desktop flag only; never registered in HTTP/tools.
        # Refuse to adopt an existing personal Owner. No shared/default password.
        state = self.status()
        marker = self.runtime.root / 'developer-identity.dpapi'
        if marker.exists():
            password = self._developer_password()
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
        services = self._open_services()
        try:
            services.readiness()
            result = services.identity.login(password, self.client)
            # Parent process only; set the original HttpOnly cookies before loading
            # the business UI. Neither password nor tokens enter renderer JS.
            return {'cookies': {'client': self.client, 'session': result.token, 'csrf': result.csrf}}
        finally:
            services.close()

    def local_access(self):
        """No password is created, stored or required in the current native app."""
        from class_os.application.local_identity import LocalIdentityBoundary, DISABLED_PASSWORD
        if not self.development:
            raise ValueError('Explicit local development required')
        state = self.status()
        marker = self.runtime.root / 'local-development.dpapi'
        legacy = self.runtime.root / 'developer-identity.dpapi'
        database = self.runtime.database('identity')
        try:
            store = PostgresIdentityStore(database)
            with database.transaction(read_only=True) as connection:
                row = connection.execute(text('SELECT owner_id,workspace_id,password_hash FROM class_os.owner_account')).mappings().one_or_none()
            previous_hash = None
            if marker.exists():
                owner_id, workspace_id = local_binding(self.runtime)
            else:
                if row is not None:
                    # One-time conversion of the former generated developer
                    # credential, preserving every workspace/business ID.
                    if not PasswordHash.recommended().verify(self._developer_password(), row['password_hash']):
                        raise ValueError('Existing identity does not match this developer instance')
                    owner_id, workspace_id = row['owner_id'], row['workspace_id']
                else:
                    owner_id, workspace_id = uuid4(), uuid4()
                payload = json.dumps({'kind': 'classmatter.local-development.v1',
                    'owner_id': str(owner_id), 'workspace_id': str(workspace_id)}).encode('utf-8')
                with marker.open('xb') as target:
                    target.write(protect(payload))
            if row is not None and row['password_hash'] != DISABLED_PASSWORD:
                if not PasswordHash.recommended().verify(self._developer_password(), row['password_hash']):
                    raise ValueError('Existing developer conversion requires review')
                previous_hash = row['password_hash']
            boundary = LocalIdentityBoundary(store, owner_id, workspace_id)
            result = boundary.connect(self.client, previous_hash=previous_hash)
            if legacy.exists():
                if legacy.is_symlink():
                    raise ValueError('Unexpected developer marker')
                legacy.unlink()
            if not state['ready']:
                self.services = self._open_services()
                self.services.identity = boundary
                self.services.worker.identity = boundary
                self.login = result
                auth = (result.token, self.client, result.csrf, workspace_id)
                self.proposal = self.services.worker.preview(*auth, InitializeConversationControl(uuid4()))
                self.operation_id = str(uuid4())
                self.approve_control(self.operation_id, self.proposal.payload_hash, True)
                self.close()
                result = boundary.connect(self.client)
            response = {'cookies': {'client': self.client, 'session': result.token, 'csrf': result.csrf}}
            if self.runtime.profile in ('workspace-chat-d3', 'classroom-work-d4'):
                from .local_model_activation import LocalModelActivation
                selected = LocalModelActivation(self.runtime.root, workspace_id).read()
                if selected is not None:
                    response['model_network'] = {'bases': [selected['base_url']], 'proxy': selected['proxy']}
            return response
        finally:
            database.close()


def local_binding(runtime):
    marker = runtime.root / 'local-development.dpapi'
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 8192:
        raise ValueError('Local workspace binding unavailable')
    value = json.loads(protect(marker.read_bytes(), decrypt=True))
    if set(value) != {'kind', 'owner_id', 'workspace_id'} or value['kind'] != 'classmatter.local-development.v1':
        raise ValueError('Unexpected local workspace binding')
    return UUID(value['owner_id']), UUID(value['workspace_id'])
