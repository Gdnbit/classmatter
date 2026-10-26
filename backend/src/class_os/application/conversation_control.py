"""Opt-in D1 controls. No HTTP composition or Agent write capability."""
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from class_os.domain.conversation_control import InitializeConversationControl, ClearConversation, decode_control
from class_os.domain.risk import Risk
from .roster import BusinessGateway, QueryGateway, CommandRejected


CONTROLS = (InitializeConversationControl, ClearConversation)
_recent = ContextVar("conversation_control_reauthentication", default=None)
_recent_refused = ContextVar("conversation_control_recent_refused", default=False)


class ControlReauthenticationRequired(CommandRejected):
    """Known pre-mutation recent-auth refusal; never a publication outcome."""


def require_recent_control(now):
    recent = _recent.get()
    if recent is None or not timedelta(0) <= now - recent <= timedelta(minutes=5):
        _recent_refused.set(True)
        raise CommandRejected()


@dataclass(frozen=True)
class ControlDecision:
    # Separate post-R1 policy: does NOT change the closed R1 risk evaluator.
    level: Risk = Risk.X
    admitted: bool = True
    requires_approval: bool = True
    policy_version: str = "d1-conversation-control.v1"


class ConversationBusinessGateway(BusinessGateway):
    def _authorized_run(self, subject, client, csrf, action, callback, **metadata):
        token = _recent.set(subject.reauthenticated_at)
        refused = _recent_refused.set(False)
        try:
            try:
                return super()._authorized_run(subject, client, csrf, action, callback, **metadata)
            except CommandRejected:
                if _recent_refused.get():
                    raise ControlReauthenticationRequired() from None
                raise
        finally:
            _recent_refused.reset(refused)
            _recent.reset(token)

    @staticmethod
    def decode_command(payload):
        if type(payload) is not dict:
            raise ValueError("Invalid command payload")
        if payload.get("command") in ("conversation.control.initialize", "conversation.clear"):
            return decode_control(payload)
        return BusinessGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        return ControlDecision() if type(command) in CONTROLS else BusinessGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        return "manage-conversation" if type(command) in CONTROLS else BusinessGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if type(command) not in CONTROLS:
            return super()._validate(tx, binding, command, now)
        require_recent_control(now)
        tx.validate_conversation_control(binding, command, now)


class ConversationQueryGateway(QueryGateway):
    @staticmethod
    def audit_purpose(action):
        return "manage-conversation" if action == "conversation.history" else QueryGateway.audit_purpose(action)

    def conversation_history(self, token, client, csrf, workspace_id, class_id, term_id, thread_id):
        def read(tx, binding, now):
            if any(type(value) is not UUID for value in (class_id, term_id, thread_id)):
                raise CommandRejected()
            return tx.conversation_history(binding, class_id, term_id, thread_id)
        return self._run((token, client, csrf, workspace_id), "conversation.history", read,
                         class_id=class_id, term_id=term_id, resource_id=thread_id)
