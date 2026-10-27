"""Explicit owned Windows D1 assembly. Never initializes an Owner or control.

Readiness inspects schema/ACL/fence metadata, not business admission. Every
authenticated body read still verifies current ISB/QG/source evidence.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
from uuid import UUID

from pwdlib import PasswordHash
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.application.conversation_interaction import ConversationInteractionQuery
from .identity import PostgresIdentityStore
from .local_runtime import LocalRuntime, protect
from .model_secrets import ModelSecrets
from .conversation_restrictions import ProtectedConversationRestrictions, RestrictionHead
from .recovery_admission_store import AdmissionStore
from .persistence.schema_inventory import validate_surface
from .persistence.role_guards import validate_role_guards
from .persistence.database import Database


@dataclass
class OwnedD1Services:
    identity_database: Database
    business_database: Database
    identity: IdentityBoundary
    worker: ConversationWorkerGateway
    query: ConversationInteractionQuery
    restrictions: ProtectedConversationRestrictions
    owner_id: UUID

    def close(self):
        self.business_database.close()
        self.identity_database.close()

    def readiness(self):
        from .source_transfer import ProtectedSourceTransfer
        from .source_retirement import ProtectedSourceRetirement
        from .target_import import ProtectedTargetImport
        from .recovery_admission import ProtectedTargetAdmission
        workspace = self.restrictions.workspace_id
        with self.business_database.transaction(read_only=True) as connection:
            _surface(connection)
            row = connection.execute(text("""SELECT owner_id,authority_id,epoch,head_hash,transfer_id
                FROM class_os.conversation_control WHERE workspace_id=:workspace"""),
                {"workspace": workspace}).mappings().one_or_none()
            if row is None or row["owner_id"] != self.owner_id or row["transfer_id"] is not None:
                raise RuntimeError("Owner control setup or recovery review required")
            compared = self.restrictions.compare(RestrictionHead(row["authority_id"], workspace, row["epoch"], row["head_hash"]))
            if compared.state != "aligned":
                raise RuntimeError("Control restrictions require review")
            if ProtectedSourceTransfer(self.restrictions).present() or ProtectedSourceRetirement(self.restrictions).present():
                raise RuntimeError("Source transfer or retirement is fenced")
            incoming = ProtectedTargetImport(self.restrictions)
            admitted = ProtectedTargetAdmission(self.restrictions)
            flags = connection.execute(text("""SELECT
                EXISTS(SELECT 1 FROM class_os.conversation_import WHERE workspace_id=:workspace),
                EXISTS(SELECT 1 FROM class_os.conversation_admission WHERE workspace_id=:workspace)"""),
                {"workspace": workspace}).one()
            present = incoming.present(), admitted.present()
            if any(flags) or any(present):
                if not all(flags) or not all(present):
                    raise RuntimeError("Pending target is not available for ordinary work")
                target, admission = incoming.read(), admitted.read()
                if (target != admission.stage.fence or target.workspace_id != workspace
                        or target.owner_id != self.owner_id):
                    raise RuntimeError("Target metadata binding is not current")
                # This is metadata readiness only. QG rechecks original SQL,
                # audit, source authors and complete admission on each read.
        with self.identity_database.transaction(read_only=True) as connection:
            current = connection.execute(text("SELECT owner_id,workspace_id FROM class_os.owner_account")).one_or_none()
            if current is None or tuple(current) != (self.owner_id, workspace):
                raise RuntimeError("Owner binding changed; restart explicitly")


def _surface(connection):
    validate_surface(connection, complete=True, profile="conversation-d1")
    validate_role_guards(connection, profile="conversation-d1")
    if connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() != "0026":
        raise RuntimeError("D1 schema is not current")
    if connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one() != "synthetic-only":
        raise RuntimeError("Synthetic-only runtime required")


def open_services(runtime):
    if os.name != "nt" or type(runtime) is not LocalRuntime or runtime.profile != "conversation-d1":
        raise ValueError("Explicit owned Windows D1 runtime required")
    runtime.configuration()  # Exact descriptor/profile/database binding.
    identity_database = runtime.database("identity")
    business_database = None
    try:
        business_database = runtime.database("runtime")
        with business_database.transaction(read_only=True) as connection:
            _surface(connection)
        with identity_database.transaction(read_only=True) as connection:
            owner = connection.execute(text("SELECT owner_id,workspace_id FROM class_os.owner_account")).one_or_none()
        if owner is None:
            raise RuntimeError("Owner must complete interactive bootstrap first")
        boundary = IdentityBoundary(PostgresIdentityStore(identity_database), PasswordHash.recommended())
        restrictions = ProtectedConversationRestrictions(runtime.root, owner.workspace_id)
        store = AdmissionStore(business_database, restrictions, model_secrets=ModelSecrets(protect))
        worker = ConversationWorkerGateway(boundary, store)
        query = ConversationInteractionQuery(boundary, store)
        return OwnedD1Services(identity_database, business_database, boundary, worker, query, restrictions, owner.owner_id)
    except Exception:
        if business_database is not None:
            business_database.close()
        identity_database.close()
        raise


def compose(settings, runtime):
    from .agent import PydanticAgentRuntime
    from .model_control import ModelController
    from class_os.interfaces.http.durable_conversation import create_durable_app
    services = open_services(runtime)
    try:
        services.readiness()  # Never auto-initialize a missing/failed witness.
        sdk = PydanticAgentRuntime(services.query)
        controller = ModelController(services.query, services.worker.store.model_secrets, sdk,
                                     allowed_bases=settings.model_api_bases)
        app = create_durable_app(settings, worker=services.worker, query=services.query,
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
