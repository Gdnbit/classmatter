"""Explicit D2 composition of existing domain gateways; no new write engine."""
from class_os.domain.documents import COMMANDS
from .documents import DocumentBusinessGateway, DocumentQueryGateway, DOCUMENT_TYPES
from .conversation_worker import ConversationWorkerGateway
from .conversation_interaction import ConversationInteractionQuery
from .roster import CommandRejected
from .classroom_work import ClassroomDecision, ClassroomQueries
from class_os.domain.classroom_work import COMMANDS as CLASSROOM_COMMANDS, COMMAND_TYPES as CLASSROOM_TYPES, decode_classroom
from class_os.domain.collaboration import COMMANDS as COLLABORATION_COMMANDS, COMMAND_TYPES as COLLABORATION_TYPES, decode_collaboration


INCOMPLETE_LIFECYCLE = frozenset({'exit_export.create', 'conversation_exit.create',
    'conversation.transfer.seal', 'conversation.transfer.retire', 'conversation.import.stage', 'conversation.import.admit'})


class WorkbenchBusinessGateway(DocumentBusinessGateway, ConversationWorkerGateway):
    @staticmethod
    def decode_command(payload):
        if type(payload) is dict and payload.get('command') in COLLABORATION_COMMANDS:
            return decode_collaboration(payload)
        if type(payload) is dict and payload.get('command') in CLASSROOM_COMMANDS:
            return decode_classroom(payload)
        if type(payload) is dict and payload.get('command') in COMMANDS:
            return DocumentBusinessGateway.decode_command(payload)
        return ConversationWorkerGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        if type(command) in COLLABORATION_TYPES:
            return ClassroomDecision()
        if type(command) in CLASSROOM_TYPES:
            return ClassroomDecision()
        if type(command) in DOCUMENT_TYPES:
            return DocumentBusinessGateway.assess_command(tx, binding, command)
        return ConversationWorkerGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        if type(command) in COLLABORATION_TYPES:
            return 'manage-class'
        if type(command) in CLASSROOM_TYPES:
            return 'manage-class'
        if type(command) in DOCUMENT_TYPES:
            return DocumentBusinessGateway.command_purpose(command, payload)
        return ConversationWorkerGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if type(command) in COLLABORATION_TYPES:
            if self.store.database.profile != 'classroom-work-d4':
                raise CommandRejected()
            return tx.validate_collaboration(binding, command, now)
        if type(command) in CLASSROOM_TYPES:
            if self.store.database.profile != 'classroom-work-d4':
                raise CommandRejected()
            return tx.validate_classroom(binding, command, now)
        if command.canonical().get('command') in INCOMPLETE_LIFECYCLE:
            raise CommandRejected()
        if type(command) in DOCUMENT_TYPES:
            return DocumentBusinessGateway._validate(tx, binding, command, now)
        return ConversationWorkerGateway._validate(self, tx, binding, command, now)


class WorkbenchQueryGateway(DocumentQueryGateway, ConversationInteractionQuery, ClassroomQueries):
    def collaboration(self, credentials, *, thread_id=None):
        if self.store.database.profile != 'classroom-work-d4':
            raise CommandRejected()
        return self._run(credentials,'collaboration.read',
            lambda tx,binding,now:tx.collaboration_read(binding,thread_id),resource_id=thread_id)

    @staticmethod
    def audit_purpose(action):
        if action in ('exam.list', 'exam.read', 'seat.read'):
            return ClassroomQueries.audit_purpose(action)
        return (DocumentQueryGateway.audit_purpose(action) if action.startswith('document.')
                else ConversationInteractionQuery.audit_purpose(action))

    def workbench_capabilities(self, token, client, csrf, workspace_id):
        return self._run((token, client, csrf, workspace_id), 'class.context',
                         lambda tx, binding, now: tx.workbench_capabilities(binding, now))
