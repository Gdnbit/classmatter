"""Explicit D2 composition of existing domain gateways; no new write engine."""
from class_os.domain.documents import COMMANDS
from .documents import DocumentBusinessGateway, DocumentQueryGateway, DOCUMENT_TYPES
from .conversation_worker import ConversationWorkerGateway
from .conversation_interaction import ConversationInteractionQuery
from .roster import CommandRejected


INCOMPLETE_LIFECYCLE = frozenset({'exit_export.create', 'conversation_exit.create',
    'conversation.transfer.seal', 'conversation.transfer.retire', 'conversation.import.stage', 'conversation.import.admit'})


class WorkbenchBusinessGateway(DocumentBusinessGateway, ConversationWorkerGateway):
    @staticmethod
    def decode_command(payload):
        if type(payload) is dict and payload.get('command') in COMMANDS:
            return DocumentBusinessGateway.decode_command(payload)
        return ConversationWorkerGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        if type(command) in DOCUMENT_TYPES:
            return DocumentBusinessGateway.assess_command(tx, binding, command)
        return ConversationWorkerGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        if type(command) in DOCUMENT_TYPES:
            return DocumentBusinessGateway.command_purpose(command, payload)
        return ConversationWorkerGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if command.canonical().get('command') in INCOMPLETE_LIFECYCLE:
            raise CommandRejected()
        if type(command) in DOCUMENT_TYPES:
            return DocumentBusinessGateway._validate(tx, binding, command, now)
        return ConversationWorkerGateway._validate(self, tx, binding, command, now)


class WorkbenchQueryGateway(DocumentQueryGateway, ConversationInteractionQuery):
    @staticmethod
    def audit_purpose(action):
        return (DocumentQueryGateway.audit_purpose(action) if action.startswith('document.')
                else ConversationInteractionQuery.audit_purpose(action))

    def workbench_capabilities(self, token, client, csrf, workspace_id):
        return self._run((token, client, csrf, workspace_id), 'class.context',
                         lambda tx, binding, now: tx.workbench_capabilities(binding, now))
