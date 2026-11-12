"""Explicit D3 startup; never initializes, migrates, resets or adopts an Owner."""
import os
from contextlib import asynccontextmanager

from pwdlib import PasswordHash
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from .durable_local_runtime import OwnedD1Services
from .identity import PostgresIdentityStore
from .local_runtime import LocalRuntime, protect
from .model_secrets import ModelSecrets
from .conversation_restrictions import ProtectedConversationRestrictions
from .persistence.schema_inventory import validate_surface, schema_profile
from .persistence.role_guards import validate_role_guards
from .documents import validate_document_integrity
from .workspace_chat import validate_workspace_chat_integrity
from .workbench import WorkbenchStore


def surface(connection, *, profile='workspace-chat-d3'):
    if profile not in ('workspace-chat-d3', 'classroom-work-d4'):
        raise ValueError('Explicit workspace profile required')
    validate_surface(connection, complete=True, profile=profile)
    validate_role_guards(connection, profile=profile)
    if (connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() != schema_profile(profile)[0]
            or connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one() != "synthetic-only"):
        raise RuntimeError("Explicit current synthetic D3 schema required")
    validate_document_integrity(connection); validate_workspace_chat_integrity(connection)
    if profile == 'classroom-work-d4':
        from .classroom_work import validate_classroom_integrity
        validate_classroom_integrity(connection)


class OwnedWorkspaceServices(OwnedD1Services):
    def surface(self, connection):
        surface(connection, profile=self.business_database.profile)


def open_services(runtime, *, local_development=False):
    if os.name != "nt" or type(runtime) is not LocalRuntime or runtime.profile not in ('workspace-chat-d3', 'classroom-work-d4'):
        raise ValueError("Explicit owned Windows D3 runtime required")
    runtime.configuration()
    if runtime.profile == 'classroom-work-d4':
        from .classroom_upgrade import verify_upgrade_receipt
    else:
        from .workspace_upgrade import verify_upgrade_receipt
    receipt = verify_upgrade_receipt(runtime)
    identity_database, business_database = runtime.database("identity"), None
    try:
        business_database = runtime.database("runtime")
        with business_database.transaction(read_only=True) as connection:
            surface(connection, profile=runtime.profile)
        with identity_database.transaction(read_only=True) as connection:
            owner = connection.execute(text("SELECT owner_id,workspace_id FROM class_os.owner_account")).one_or_none()
        if owner is None or str(owner.owner_id) != receipt["owner_id"] or str(owner.workspace_id) != receipt["workspace_id"]:
            raise RuntimeError("Existing owner binding required")
        if local_development is True:
            from .native_setup import local_binding
            from class_os.application.local_identity import LocalIdentityBoundary
            local_owner, local_workspace = local_binding(runtime)
            if (local_owner, local_workspace) != (owner.owner_id, owner.workspace_id):
                raise ValueError("Local workspace binding mismatch")
            identity = LocalIdentityBoundary(PostgresIdentityStore(identity_database), local_owner, local_workspace)
        else:
            identity = IdentityBoundary(PostgresIdentityStore(identity_database), PasswordHash.recommended())
        restrictions = ProtectedConversationRestrictions(runtime.root, owner.workspace_id)
        store = WorkbenchStore(business_database, restrictions, model_secrets=ModelSecrets(protect))
        result = OwnedWorkspaceServices(identity_database, business_database, identity,
            WorkbenchBusinessGateway(identity, store), WorkbenchQueryGateway(identity, store), restrictions, owner.owner_id)
        result.readiness()
        return result
    except Exception:
        if business_database is not None:
            business_database.close()
        identity_database.close()
        raise


def compose(settings, runtime, *, local_development=False):
    from .agent import PydanticAgentRuntime
    from .model_control import ModelController
    from .local_model_activation import LocalModelActivation
    from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
    services = open_services(runtime, local_development=local_development)
    try:
        from .operator_run_metadata import for_runtime
        sdk = PydanticAgentRuntime(services.query, timeout=45,
            diagnostics=for_runtime(runtime, local_development=local_development))
        controller = ModelController(services.query, services.worker.store.model_secrets, sdk,
            allowed_bases=settings.model_api_bases, proxy=settings.model_api_proxy,
            activation=LocalModelActivation(runtime.root, services.restrictions.workspace_id,
                proxy=settings.model_api_proxy) if local_development else None)
        app = create_workspace_chat_app(settings, worker=services.worker, query=services.query, sdk=sdk,
            readiness=services.readiness, model_controller=controller)
    except Exception:
        services.close(); raise
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            services.close()
    app.router.lifespan_context = lifespan
    return app
