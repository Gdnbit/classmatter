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
        legacy, _ = partition_audit(audit, str(binding['workspace_id']), str(binding['actor_id']), now)
        bundle = build_package(binding['workspace_id'], binding['actor_id'], now, core, conversations, proof, legacy, recovery)
        verify_native_result_commits(self._connection, binding, conversations)
        return bundle
