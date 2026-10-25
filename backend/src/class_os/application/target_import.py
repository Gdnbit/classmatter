"""Human-only isolated import, using live authorized source QG metadata."""
from contextvars import ContextVar
from uuid import UUID

from class_os.domain.target_import import StageConversationImport, decode_import
from .conversation_control import ConversationBusinessGateway, ControlDecision, require_recent_control
from .roster import QueryGateway, CommandRejected
from .source_transfer import SourceTransferQueryGateway


_target_operation = ContextVar("classmatter_target_import_operation", default=None)


def target_operation_permitted(store, binding, action, proposal_id):
    return (action in {"command.preview", "command.approve", "command.reject", "command.commit", "command.status", "conversation.transfer.proof"}
            and _target_operation.get() == (id(store), binding["workspace_id"], binding["actor_id"], action, proposal_id))


class AuthorizedSourceReader:
    """Trusted same-host composition; credentials are not persisted or exported."""
    def __init__(self, query, credentials, attempt_id):
        if type(query) is not SourceTransferQueryGateway or type(credentials) is not tuple or len(credentials) != 4:
            raise ValueError("Authorized live source QG required")
        self.query, self.credentials, self.attempt_id = query, credentials, attempt_id

    def current(self):
        return self.query.committed_source(*self.credentials, self.attempt_id)


class TargetOperation:
    def _authorized_run(self, subject, client, csrf, action, callback, **metadata):
        token = _target_operation.set((id(self.store), subject.workspace_id, subject.owner_id, action, metadata.get("proposal_id")))
        try:
            return super()._authorized_run(subject, client, csrf, action, callback, **metadata)
        finally:
            _target_operation.reset(token)


class TargetImportGateway(TargetOperation, ConversationBusinessGateway):
    decode_command = staticmethod(decode_import)

    @staticmethod
    def command_purpose(command, payload):
        return "exit-recovery"

    @staticmethod
    def assess_command(tx, binding, command):
        return ControlDecision(policy_version="d1-target-import.v1")

    def _validate(self, tx, binding, command, now):
        if type(command) is not StageConversationImport:
            raise CommandRejected()
        require_recent_control(now)
        tx.validate_target_import(binding, command, now)


class TargetImportQueryGateway(TargetOperation, QueryGateway):
    """Only existing status metadata may be read while target is pending."""

    @staticmethod
    def audit_purpose(action):
        return "exit-recovery" if action == "conversation.transfer.proof" else QueryGateway.audit_purpose(action)

    def committed_stage(self, token, client, csrf, workspace_id, attempt_id):
        def read(tx, binding, now):
            if type(attempt_id) is not UUID:
                raise CommandRejected()
            return tx.committed_stage(binding, attempt_id)
        return self._run((token, client, csrf, workspace_id), "conversation.transfer.proof", read, resource_id=attempt_id)
