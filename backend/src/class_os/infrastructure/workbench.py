"""Native D2 store composition. Imported/retired instances remain unavailable."""
from datetime import date, datetime
from uuid import UUID

import rfc8785
from sqlalchemy import text

from class_os.application.documents import DOCUMENT_TYPES
from class_os.application.workbench import INCOMPLETE_LIFECYCLE
from class_os.application.roster import CommandRejected
from .documents import DocumentStore, DocumentTransaction
from .conversation_control import ConversationTransaction
from .recovery_admission_store import AdmissionTransaction
from .persistence.schema_inventory import schema_profile


class WorkbenchStore(DocumentStore):
    def __init__(self, database, restrictions, *, model_secrets=None):
        super().__init__(database, restrictions)
        self.model_secrets = model_secrets
        self.retirement = None  # D2 import/transfer has no admission yet.

    def _transaction(self, connection):
        if self.database.profile == 'classroom-work-d4':
            if connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() != schema_profile('classroom-work-d4')[0]:
                raise RuntimeError('Explicit classroom work schema required')
            from .builtin_summary_store import BuiltinSummaryTransaction
            return BuiltinSummaryTransaction(connection, self)
        if self.database.profile == 'workspace-chat-d3':
            if connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() != '0028':
                raise RuntimeError('Explicit workspace chat schema required')
            from .workspace_chat import WorkspaceChatTransaction
            return WorkspaceChatTransaction(connection, self)
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
        # Online reconstruction is not a complete export. Audit traffic must
        # not consume an export-file budget before a small history can open.
        from class_os.domain.conversation_exit_v6 import build_package
        from .conversation_worker import verify_native_result_commits
        core, conversations, proof, recovery, budget = snapshot if snapshot is not None else self._snapshot(binding, now)
        if recovery['conversation_import'] or recovery['conversation_admission']:
            raise CommandRejected()
        audit = self._read_result_audit(binding, now, conversations, budget)
        bundle = build_package(binding['workspace_id'], binding['actor_id'], now, core, conversations, proof, audit, recovery)
        verify_native_result_commits(self._connection, binding, conversations)
        return bundle

    def _read_result_audit(self, binding, now, conversations, budget):
        from class_os.domain.exit_package import AUDIT_COLUMNS
        from class_os.domain.conversation_exit import MAX_BYTES, MAX_ROWS
        from class_os.domain.workbench_audit import partition_audit
        sources = {row['receipt_id'] for row in conversations['conversation_query_source']}
        runs = {row['run_id'] for row in conversations['conversation_run'] if row['state'] == 'completed'}
        selected = []
        # Fixed public columns only. Server-side chunks bound memory; the
        # existing serialized business transaction holds the snapshot stable.
        # The schema's audit PK prevents duplicate identities across chunks.
        result = self._connection.execute(text(
            'SELECT ' + ','.join(AUDIT_COLUMNS) + ' FROM class_os.business_audit '
            'WHERE workspace_id=:workspace ORDER BY occurred_at,event_id').execution_options(stream_results=True),
            {'workspace': binding['workspace_id']})
        try:
            for chunk in result.mappings().partitions(128):
                rows = [{key: str(value) if isinstance(value, UUID) else value.isoformat()
                         if isinstance(value, (date, datetime)) else value for key, value in row.items()} for row in chunk]
                legacy, _ = partition_audit(rows, str(binding['workspace_id']), str(binding['actor_id']), now,
                    classroom=self._store.database.profile == 'classroom-work-d4')
                # Validate ALL rows above, including unrelated rows in the last
                # chunk. Carry every matching source/completion row so duplicate
                # or corrupted evidence cannot disappear through filtering.
                for row in legacy:
                    if row['event_id'] in sources or row['action'] == 'command.commit' and row['resource_id'] in runs:
                        selected.append(row)
                        budget[0] += len(rfc8785.dumps(row)) + 1
                        if len(selected) > MAX_ROWS or budget[0] > MAX_BYTES:
                            raise CommandRejected()
        finally:
            result.close()
        return selected

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
        legacy, document_audit = partition_audit(audit, str(binding['workspace_id']), str(binding['actor_id']), now,
            classroom=self._store.database.profile == 'classroom-work-d4')
        bundle = build_package(binding['workspace_id'], binding['actor_id'], now, core, conversations, proof, legacy, recovery)
        verify_native_result_commits(self._connection, binding, conversations)
        return bundle, document_audit, budget

    def _workbench_data_bundle(self, binding, now):
        if self._store.database.profile != 'workbench-d2':
            raise CommandRejected()  # Old document archive cannot omit D3 chat.
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
