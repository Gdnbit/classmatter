"""Human-only opt-in D1 export; not an Agent tool, import or activation."""
from uuid import UUID

from class_os.domain.conversation_exit import CreateConversationExit
from .conversation_control import ConversationBusinessGateway, ConversationQueryGateway, ControlDecision, require_recent_control
from .roster import CommandRejected


class ConversationExitBusinessGateway(ConversationBusinessGateway):
    @staticmethod
    def decode_command(payload):
        if type(payload) is dict and payload.get("command") == "conversation_exit.create":
            if set(payload) != {"command", "export_id", "expected_snapshot_hash"} or type(payload["export_id"]) is not str:
                raise ValueError("Invalid conversation exit command")
            command = CreateConversationExit(UUID(payload["export_id"]), payload["expected_snapshot_hash"])
            if command.canonical() != payload:
                raise ValueError("Noncanonical conversation exit command")
            return command
        return ConversationBusinessGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        return ControlDecision() if type(command) is CreateConversationExit else ConversationBusinessGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        return "exit-recovery" if type(command) is CreateConversationExit else ConversationBusinessGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if type(command) is CreateConversationExit:
            require_recent_control(now)
            tx.validate_conversation_exit(binding, command, now)
            return
        return super()._validate(tx, binding, command, now)


class ConversationExitQueryGateway(ConversationQueryGateway):
    def conversation_exit_summary(self, *credentials):
        return self._run(credentials, "exit.conversation.summary", lambda tx, binding, now: tx.conversation_exit_summary(binding, now))

    def conversation_exit_download(self, token, client, csrf, workspace_id, export_id):
        def read(tx, binding, now):
            if type(export_id) is not UUID:
                raise CommandRejected()
            return tx.conversation_exit_artifact(binding, export_id, now)
        return self._run((token, client, csrf, workspace_id), "exit.conversation.download", read, resource_id=export_id)
