"""Human-only source freeze. No target import, admission or automatic thaw."""
from contextvars import ContextVar
from uuid import UUID

from class_os.domain.source_transfer import SealConversationSource, decode_seal
from .conversation_exit import ConversationExitBusinessGateway
from .conversation_control import ControlDecision, require_recent_control
from .roster import CommandRejected, QueryGateway


_source_operation = ContextVar("classmatter_source_transfer_operation", default=None)


def source_operation_permitted(store, binding, action, proposal_id):
    return (action in {"command.preview", "command.approve", "command.reject", "command.commit", "command.status", "conversation.transfer.proof"}
            and _source_operation.get() == (id(store), binding["workspace_id"], binding["actor_id"], action, proposal_id))


class SourceOperation:
    def _authorized_run(self, subject, client, csrf, action, callback, **metadata):
        marker = _source_operation.set((id(self.store), subject.workspace_id, subject.owner_id, action, metadata.get("proposal_id")))
        try:
            return super()._authorized_run(subject, client, csrf, action, callback, **metadata)
        finally:
            _source_operation.reset(marker)


class SourceTransferQueryGateway(SourceOperation, QueryGateway):
    """Only status and committed-freeze metadata get scoped exemptions."""

    @staticmethod
    def audit_purpose(action):
        return "exit-recovery" if action == "conversation.transfer.proof" else QueryGateway.audit_purpose(action)

    def committed_source(self, token, client, csrf, workspace_id, attempt_id):
        def read(tx, binding, now):
            if type(attempt_id) is not UUID:
                raise CommandRejected()
            return tx.committed_source(binding, attempt_id)
        return self._run((token, client, csrf, workspace_id), "conversation.transfer.proof", read, resource_id=attempt_id)


class SourceTransferGateway(SourceOperation, ConversationExitBusinessGateway):
    decode_command = staticmethod(decode_seal)

    @staticmethod
    def command_purpose(command, payload):
        return "exit-recovery"

    @staticmethod
    def assess_command(tx, binding, command):
        return ControlDecision(policy_version="d1-source-transfer.v1")

    def _validate(self, tx, binding, command, now):
        if type(command) is not SealConversationSource:
            raise CommandRejected()
        require_recent_control(now)
        tx.validate_source_seal(binding, command, now)
