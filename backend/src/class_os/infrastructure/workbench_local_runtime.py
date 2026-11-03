"""Explicit native D2 services in the existing owned root; no bootstrap/reset."""
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
from .persistence.schema_inventory import validate_surface
from .persistence.role_guards import validate_role_guards
from .documents import validate_document_integrity
from .workbench import WorkbenchStore


def surface(connection):
    validate_surface(connection, complete=True, profile='workbench-d2')
    validate_role_guards(connection, profile='workbench-d2')
    if (connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() != '0027'
            or connection.execute(text('SELECT data_mode FROM class_os.database_state WHERE singleton=true')).scalar_one() != 'synthetic-only'):
        raise RuntimeError('Explicit current synthetic D2 schema required')
    validate_document_integrity(connection)


class OwnedWorkbenchServices(OwnedD1Services):
    def surface(self, connection):
        surface(connection)

    def readiness(self):
        super().readiness()
        from .target_import import ProtectedTargetImport
        from .recovery_admission import ProtectedTargetAdmission
        if (ProtectedTargetImport(self.restrictions).present() or ProtectedTargetAdmission(self.restrictions).present()):
            raise RuntimeError('D2 target admission is not available')
        with self.business_database.transaction(read_only=True) as connection:
            if connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.conversation_import)
                OR EXISTS(SELECT 1 FROM class_os.conversation_admission)''')).scalar_one():
                raise RuntimeError('D2 target admission is not available')


def open_services(runtime):
    if os.name != 'nt' or type(runtime) is not LocalRuntime or runtime.profile != 'workbench-d2':
        raise ValueError('Explicit owned Windows D2 runtime required')
    runtime.configuration()
    from .workbench_upgrade import verify_upgrade_receipt
    receipt = verify_upgrade_receipt(runtime)
    identity_database, business_database = runtime.database('identity'), None
    try:
        business_database = runtime.database('runtime')
        with business_database.transaction(read_only=True) as connection:
            surface(connection)
        with identity_database.transaction(read_only=True) as connection:
            owner = connection.execute(text('SELECT owner_id,workspace_id FROM class_os.owner_account')).one_or_none()
        if (owner is None or str(owner.owner_id) != receipt['owner_id'] or str(owner.workspace_id) != receipt['workspace_id']):
            raise RuntimeError('Existing owner required; no D2 bootstrap')
        identity = IdentityBoundary(PostgresIdentityStore(identity_database), PasswordHash.recommended())
        restrictions = ProtectedConversationRestrictions(runtime.root, owner.workspace_id)
        store = WorkbenchStore(business_database, restrictions, model_secrets=ModelSecrets(protect))
        result = OwnedWorkbenchServices(identity_database, business_database, identity,
            WorkbenchBusinessGateway(identity, store), WorkbenchQueryGateway(identity, store), restrictions, owner.owner_id)
        result.readiness()
        return result
    except Exception:
        if business_database is not None:
            business_database.close()
        identity_database.close()
        raise


def compose(settings, runtime):
    """Explicit same-world service, without migration, bootstrap or reset."""
    from .agent import PydanticAgentRuntime
    from .model_control import ModelController
    from class_os.interfaces.http.workbench import create_workbench_app
    services = open_services(runtime)
    try:
        sdk = PydanticAgentRuntime(services.query)
        controller = ModelController(services.query, services.worker.store.model_secrets, sdk,
            allowed_bases=settings.model_api_bases, proxy=settings.model_api_proxy)
        app = create_workbench_app(settings, worker=services.worker, query=services.query,
            sdk=sdk, readiness=services.readiness, model_controller=controller)
    except Exception:
        services.close()
        raise

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            services.close()

    app.router.lifespan_context = lifespan
    return app
