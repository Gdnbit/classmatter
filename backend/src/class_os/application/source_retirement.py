"""Human retirement; the target is observed through its current authorized QG."""
from uuid import UUID

from class_os.domain.source_retirement import RetireConversationSource, decode_retirement
from .conversation_control import ControlDecision, require_recent_control
from .roster import CommandRejected
from .source_transfer import SourceTransferGateway, SourceTransferQueryGateway
from .target_import import TargetImportQueryGateway


class AuthorizedTargetReader:
    def __init__(self, query, credentials, attempt_id):
        if (type(query) is not TargetImportQueryGateway or type(credentials) is not tuple or len(credentials) != 4
                or type(attempt_id) is not UUID):
            raise ValueError("Authorized live target QG required")
        self.query, self.credentials, self.attempt_id = query, credentials, attempt_id

    def current(self):
        return self.query.committed_stage(*self.credentials, self.attempt_id)


class SourceRetirementGateway(SourceTransferGateway):
    decode_command = staticmethod(decode_retirement)

    @staticmethod
    def assess_command(tx, binding, command):
        return ControlDecision(policy_version="d1-source-retirement.v1")

    def _validate(self, tx, binding, command, now):
        if type(command) is not RetireConversationSource:
            raise CommandRejected()
        require_recent_control(now)
        tx.validate_source_retirement(binding, command, now)


class SourceRetirementQueryGateway(SourceTransferQueryGateway):
    def committed_retirement(self, token, client, csrf, workspace_id, attempt_id):
        def read(tx, binding, now):
            if type(attempt_id) is not UUID:
                raise CommandRejected()
            return tx.committed_retirement(binding, attempt_id)
        return self._run((token, client, csrf, workspace_id), "conversation.transfer.proof", read, resource_id=attempt_id)
