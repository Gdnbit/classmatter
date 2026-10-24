"""Fixed source seal SQL only inside existing ISB/BCG/audit transactions."""
from uuid import UUID, uuid4

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.roster import Receipt
from class_os.domain.source_transfer import SealConversationSource, SourceFence
from .conversation_exit import ConversationExitStore, ConversationExitTransaction
from .source_transfer import ProtectedSourceTransfer, TransferUnavailable


class SourceTransferStore(ConversationExitStore):
    def _conversation_transaction(self, connection):
        return SourceTransferTransaction(connection, self)


class SourceTransferTransaction(ConversationExitTransaction):
    def validate_source_seal(self, binding, command, now):
        if type(command) is not SealConversationSource:
            raise CommandRejected()
        port = ProtectedSourceTransfer(self._store.restrictions)
        try:
            if (command.target_workspace_id == binding["workspace_id"] or command.target_owner_id == binding["actor_id"]
                    or command.target_binding == self._store.restrictions._binding(self._store.restrictions._root())):
                raise CommandRejected()
            control = self._connection.execute(text("""SELECT transfer_id,updated_at FROM class_os.conversation_control
                WHERE workspace_id=:workspace_id AND owner_id=:actor_id"""), binding).mappings().one_or_none()
            if control is None or control["transfer_id"] is not None or now < control["updated_at"]:
                raise CommandRejected()
            artifact = self.conversation_exit_artifact(binding, command.export_id, now)
            if (artifact.package_hash != command.package_hash
                    or self.conversation_exit_summary(binding, now).snapshot_hash != artifact.bundle["snapshot_hash"]
                    or self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.conversation_run
                        WHERE workspace_id=:workspace_id AND state IN ('queued','running','cancel_requested'))"""), binding).scalar_one()):
                raise CommandRejected()
            proof = artifact.bundle["restriction_evidence"]
            fence = SourceFence(binding["workspace_id"], binding["actor_id"], UUID(proof["authority_id"]), proof["epoch"],
                                proof["source_head_hash"], command, now)
            if port.present():
                existing = port.read()
                if (existing.command != command or existing.workspace_id != fence.workspace_id or existing.owner_id != fence.owner_id
                        or existing.authority_id != fence.authority_id or existing.restriction_epoch != fence.restriction_epoch
                        or existing.restriction_hash != fence.restriction_hash or not control["updated_at"] <= existing.created_at <= now):
                    raise CommandRejected()
                fence = existing
            return fence
        except (TransferUnavailable, ValueError):
            raise CommandRejected() from None

    def apply(self, binding, command, now):
        if type(command) is not SealConversationSource:
            return super().apply(binding, command, now)
        fence = self.validate_source_seal(binding, command, now)
        port = ProtectedSourceTransfer(self._store.restrictions)
        try:
            digest = port.seal(fence)
        except TransferUnavailable:
            raise CommandRejected() from None
        self._mutate(text("""UPDATE class_os.conversation_control SET transfer_id=:attempt,transfer_hash=:hash,
            transfer_at=:at,updated_at=:at WHERE workspace_id=:workspace_id AND owner_id=:actor_id
            AND transfer_id IS NULL AND authority_id=:authority AND epoch=:epoch AND head_hash=:head"""),
            {**binding, "attempt": command.attempt_id, "hash": digest, "at": fence.created_at, "authority": fence.authority_id,
             "epoch": fence.restriction_epoch, "head": fence.restriction_hash})
        return Receipt(uuid4(), command.attempt_id, 1)
