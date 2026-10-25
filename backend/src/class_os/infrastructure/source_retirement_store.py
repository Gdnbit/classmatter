"""Retirement uses existing ISB/BCG/receipt/audit storage, not a second writer."""
from uuid import uuid4

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.source_retirement import AuthorizedTargetReader
from class_os.domain.roster import Receipt
from class_os.domain.source_retirement import RetireConversationSource, RetirementFence, CommittedRetirement
from .source_transfer_store import SourceTransferStore, SourceTransferTransaction
from .source_retirement import ProtectedSourceRetirement, RetirementUnavailable


class SourceRetirementStore(SourceTransferStore):
    def __init__(self, database, restrictions, target=None):
        if target is not None and type(target) is not AuthorizedTargetReader:
            raise ValueError("Live authorized target reader required")
        super().__init__(database, restrictions)
        self.target = target

    def _conversation_transaction(self, connection):
        return SourceRetirementTransaction(connection, self)


class SourceRetirementTransaction(SourceTransferTransaction):
    def validate_source_retirement(self, binding, command, now):
        if type(command) is not RetireConversationSource or self._store.target is None:
            raise CommandRejected()
        source = self.committed_source(binding, command.attempt_id, allow_retired=True)
        if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.command_proposal
            WHERE workspace_id=:workspace_id AND actor_id=:actor_id AND command_type='conversation.transfer.retire'
            AND state='committed')"""), binding).scalar_one():
            # Lost replies replay the original receipt before validation.
            # A fresh proposal must never manufacture a second retirement.
            raise CommandRejected()
        stage = self._store.target.current()
        port = ProtectedSourceRetirement(self._store.restrictions)
        try:
            fence = RetirementFence(source, stage, command, now)
            if port.present():
                prior = port.read()
                if (prior.source != source or prior.stage != stage or prior.command != command
                        or not stage.imported_at <= prior.created_at <= now):
                    raise CommandRejected()
                fence = prior
            return fence
        except (ValueError, RetirementUnavailable):
            raise CommandRejected() from None

    def committed_retirement(self, binding, attempt_id):
        try:
            port = ProtectedSourceRetirement(self._store.restrictions)
            fence = port.read()
            source = self.committed_source(binding, attempt_id, allow_retired=True)
            receipts = self._connection.execute(text("""SELECT r.receipt_id,r.resource_version,r.committed_at,p.payload
                FROM class_os.command_receipt r JOIN class_os.command_proposal p USING(proposal_id)
                WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND r.resource_id=:attempt
                AND p.command_type='conversation.transfer.retire' AND p.state='committed' LIMIT 2"""),
                {**binding, "attempt": attempt_id}).mappings().all()
            if (fence.source != source or fence.command.attempt_id != attempt_id or len(receipts) != 1
                    or receipts[0]["resource_version"] != 2 or receipts[0]["payload"] != fence.command.canonical()
                    or receipts[0]["committed_at"] < fence.created_at):
                raise CommandRejected()
            return CommittedRetirement(fence, port.digest(fence), receipts[0]["receipt_id"])
        except RetirementUnavailable:
            raise CommandRejected() from None

    def apply(self, binding, command, now):
        if type(command) is not RetireConversationSource:
            return super().apply(binding, command, now)
        fence = self.validate_source_retirement(binding, command, now)
        try:
            ProtectedSourceRetirement(self._store.restrictions).retire(fence)
        except RetirementUnavailable:
            raise CommandRejected() from None
        # SQL receipt and trusted audit are committed by the existing BCG.
        # If either fails, the external file remains and the source stays frozen.
        return Receipt(uuid4(), command.attempt_id, 2)
