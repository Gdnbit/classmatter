"""Native D2 store composition. Imported/retired instances remain unavailable."""
from sqlalchemy import text

from class_os.application.documents import DOCUMENT_TYPES
from class_os.application.workbench import INCOMPLETE_LIFECYCLE
from class_os.application.roster import CommandRejected
from .documents import DocumentStore, DocumentTransaction
from .conversation_control import ConversationTransaction
from .recovery_admission_store import AdmissionTransaction


class WorkbenchStore(DocumentStore):
    def __init__(self, database, restrictions, *, model_secrets=None):
        super().__init__(database, restrictions)
        self.model_secrets = model_secrets
        self.retirement = None  # D2 import/transfer has no admission yet.

    def _transaction(self, connection):
        if connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() != '0027':
            raise RuntimeError('Explicit workbench schema required')
        return WorkbenchTransaction(connection, self)


class WorkbenchTransaction(DocumentTransaction, AdmissionTransaction):
    def workbench_capabilities(self, binding, now):
        self._proof(binding)
        self.verified_result_bundle(binding, now)
        return {'profile': 'workbench-d2', 'data_mode': 'synthetic-only',
                'history_protocol': 'classmatter.conversation-history.v2',
                'document_protocol': 'classmatter.document.v1', 'complete_exit': False}

    def authorize_boundary(self, binding, action, proposal_id):
        # Preserve the original protected-root, pending clear and source fences.
        ConversationTransaction.authorize_boundary(self, binding, action, proposal_id)
        self._anchor(binding)
        from .target_import import ProtectedTargetImport
        from .recovery_admission import ProtectedTargetAdmission
        if (ProtectedTargetImport(self._store.restrictions).present()
                or ProtectedTargetAdmission(self._store.restrictions).present()
                or self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.conversation_import)
                    OR EXISTS(SELECT 1 FROM class_os.conversation_admission)
                    OR EXISTS(SELECT 1 FROM class_os.conversation_control WHERE transfer_id IS NOT NULL)''')).scalar_one()):
            raise CommandRejected()
        if action.startswith('exit.') or action == 'conversation.transfer.proof':
            raise CommandRejected()  # Never return an old package omitting D2.
        if proposal_id is not None and action != 'command.status':
            proposal = self.proposal(binding['workspace_id'], proposal_id)
            if not proposal or proposal['payload'].get('command') in INCOMPLETE_LIFECYCLE:
                raise CommandRejected()

    def apply(self, binding, command, now):
        if type(command) in DOCUMENT_TYPES:
            return DocumentTransaction.apply(self, binding, command, now)
        return AdmissionTransaction.apply(self, binding, command, now)

    def verified_result_bundle(self, binding, now, snapshot=None):
        return self._verified_workbench_components(binding, now, snapshot)[0]

    def _verified_workbench_components(self, binding, now, snapshot=None):
        # Private D1 conversation component proof only. Public legacy exit and
        # transfer are refused above; never present this as the whole D2 world.
        from class_os.domain.exit_package import AUDIT_COLUMNS
        from class_os.domain.workbench_audit import partition_audit
        from class_os.domain.conversation_exit_v6 import build_package
        from .conversation_worker import verify_native_result_commits
        core, conversations, proof, recovery, budget = snapshot if snapshot is not None else self._snapshot(binding, now)
        if recovery['conversation_import'] or recovery['conversation_admission']:
            raise CommandRejected()
        audit = self._collection(binding, 'business_audit', AUDIT_COLUMNS, ('occurred_at', 'event_id'), budget)
        legacy, document_audit = partition_audit(audit, str(binding['workspace_id']), str(binding['actor_id']), now)
        bundle = build_package(binding['workspace_id'], binding['actor_id'], now, core, conversations, proof, legacy, recovery)
        verify_native_result_commits(self._connection, binding, conversations)
        return bundle, document_audit, budget

    def _workbench_data_bundle(self, binding, now):
        # Internal only: no Query Gateway/HTTP/tool export permission added.
        # Reuse the original serialized business transaction and fixed SQL
        # collector; no arbitrary table names, JSON rows or truncated pages.
        if self._now_for_admission() != now:
            raise CommandRejected()
        self.authorize_boundary(binding, 'class.context', None)
        from .source_transfer import ProtectedSourceTransfer
        from .source_retirement import ProtectedSourceRetirement
        from .target_import import ProtectedTargetImport
        from .recovery_admission import ProtectedTargetAdmission
        if any(port(self._store.restrictions).present() for port in
               (ProtectedSourceTransfer, ProtectedSourceRetirement, ProtectedTargetImport, ProtectedTargetAdmission)):
            raise CommandRejected()
        from class_os.domain.workbench_export import DOCUMENT_COLUMNS, DOCUMENT_KEYS, build_package
        component, audit, budget = self._verified_workbench_components(binding, now)
        documents = {table: self._collection(binding, table, columns, DOCUMENT_KEYS[table], budget)
                     for table, columns in DOCUMENT_COLUMNS.items()}
        return build_package(component, documents, audit)
