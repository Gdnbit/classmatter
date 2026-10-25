"""Opt-in human admission and explicitly author-aware D1 query composition."""
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from class_os.domain.recovery_admission import AdmitConversationTarget, decode_admission
from .conversation_control import ControlDecision, require_recent_control
from .conversation_exit import ConversationExitBusinessGateway, ConversationExitQueryGateway
from .source_retirement import SourceRetirementQueryGateway
from .roster import CommandRejected


_admission = ContextVar("classmatter_admission_operation", default=None)
_attributed = ContextVar("classmatter_attributed_read", default=None)
BODY_ACTIONS = frozenset({"activity.today", "student.timeline", "conversation.history"})
COMMAND_ACTIONS = frozenset({"command.preview", "command.approve", "command.reject", "command.commit"})


def admission_operation_permitted(store, binding, action, proposal_id):
    return (action in COMMAND_ACTIONS | {"command.status", "conversation.transfer.proof"}
            and _admission.get() == (id(store), binding["workspace_id"], binding["actor_id"], action, proposal_id))


def attributed_read_permitted(store, binding, action):
    return action in BODY_ACTIONS and _attributed.get() == (id(store), binding["workspace_id"], binding["actor_id"], action)


class AuthorizedRetirementReader:
    def __init__(self, query, credentials, attempt_id):
        if (type(query) is not SourceRetirementQueryGateway or type(credentials) is not tuple or len(credentials) != 4
                or type(attempt_id) is not UUID):
            raise ValueError("Current authorized source retirement QG required")
        self.query, self.credentials, self.attempt_id = query, credentials, attempt_id

    def current(self):
        return self.query.committed_retirement(*self.credentials, self.attempt_id)


@dataclass(frozen=True)
class AdmissionSummary:
    attempt_id: UUID
    stage_hash: str
    origins_hash: str
    origin_count: int


class AdmissionOperation:
    def _authorized_run(self, subject, client, csrf, action, callback, **metadata):
        token = _admission.set((id(self.store), subject.workspace_id, subject.owner_id, action, metadata.get("proposal_id")))
        try:
            return super()._authorized_run(subject, client, csrf, action, callback, **metadata)
        finally:
            _admission.reset(token)


class AdmissionGateway(AdmissionOperation, ConversationExitBusinessGateway):
    @staticmethod
    def decode_command(payload):
        if type(payload) is dict and payload.get("command") == "conversation.import.admit":
            return decode_admission(payload)
        return ConversationExitBusinessGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        return ControlDecision(policy_version="d1-target-admission.v1") if type(command) is AdmitConversationTarget else ConversationExitBusinessGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        return "exit-recovery" if type(command) is AdmitConversationTarget else ConversationExitBusinessGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if type(command) is AdmitConversationTarget:
            require_recent_control(now)
            tx.validate_admission(binding, command, now)
            return
        if not tx.has_committed_admission(binding):
            raise CommandRejected()
        return super()._validate(tx, binding, command, now)


class AdmissionQueryGateway(AdmissionOperation, ConversationExitQueryGateway):
    @staticmethod
    def audit_purpose(action):
        return "exit-recovery" if action == "conversation.transfer.proof" else ConversationExitQueryGateway.audit_purpose(action)

    def _authorized_run(self, subject, client, csrf, action, callback, **metadata):
        token = _attributed.set((id(self.store), subject.workspace_id, subject.owner_id, action))
        try:
            return super()._authorized_run(subject, client, csrf, action, callback, **metadata)
        finally:
            _attributed.reset(token)

    def admission_summary(self, token, client, csrf, workspace_id, attempt_id):
        def read(tx, binding, now):
            if type(attempt_id) is not UUID:
                raise CommandRejected()
            return tx.admission_summary(binding, attempt_id, now)
        return self._run((token, client, csrf, workspace_id), "conversation.transfer.proof", read, resource_id=attempt_id)
