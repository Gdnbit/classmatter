"""Human interaction BCG composition. Agent tools never receive this handle."""
from contextvars import ContextVar
from datetime import timedelta
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from class_os.domain.conversation_interaction import (CreateConversation, RenameConversation, ArchiveConversation,
    EnqueueConversation, decode_interaction)
from class_os.domain.durable_conversation import ConversationScope, SendIntent
from class_os.domain.roster import Proposal, CommandStatus, name
from class_os.domain.exit_package import checksum
from class_os.domain.risk import Risk
from .conversation_control import ControlDecision
from .conversation_exit import ConversationExitBusinessGateway
from .recovery_admission import AdmissionGateway, AdmissionQueryGateway
from .roster import CommandRejected, fingerprint


INTERACTIONS = (CreateConversation, RenameConversation, ArchiveConversation, EnqueueConversation)
_input = ContextVar("classmatter_human_send_input", default=None)
_title = ContextVar("classmatter_human_conversation_title", default=None)


def current_human_title(store, binding, command):
    candidate = _title.get()
    if (type(candidate) is not tuple or len(candidate) != 5
            or candidate[:3] != (id(store), binding["workspace_id"], binding["actor_id"])
            or type(command) not in (CreateConversation, RenameConversation)
            or candidate[3] != command.canonical() or checksum(candidate[4]) != command.title_hash):
        raise CommandRejected()
    return candidate[4]


def current_send_input(store, binding, command):
    candidate = _input.get()
    if (type(candidate) is not tuple or len(candidate) != 4
            or candidate[:3] != (id(store), binding["workspace_id"], binding["actor_id"])
            or type(command) is not EnqueueConversation or not command.matches(candidate[3])):
        raise CommandRejected()
    return candidate[3]


def send_receipt_key(scope, thread_id, request_id):
    return uuid5(NAMESPACE_URL, f"classmatter/human-enqueue/{scope.workspace_id}/{scope.owner_id}/{thread_id}/{request_id}")


class ConversationInteractionGateway(AdmissionGateway):
    def create_conversation(self, token, client, csrf, workspace_id, class_id, term_id, thread_id, request_id, title, student_id=None):
        try:
            name(title)
            command = CreateConversation(thread_id, class_id, term_id, checksum(title), student_id)
        except ValueError:
            raise CommandRejected() from None
        return self._title_write((token, client, csrf, workspace_id), command, request_id, title)

    def rename_conversation(self, token, client, csrf, workspace_id, class_id, term_id, thread_id, request_id, expected_version, title):
        try:
            name(title)
            command = RenameConversation(thread_id, class_id, term_id, expected_version, checksum(title))
        except ValueError:
            raise CommandRejected() from None
        return self._title_write((token, client, csrf, workspace_id), command, request_id, title)

    def _title_write(self, credentials, command, key, title):
        def save(tx, binding, now):
            if type(key) is not UUID or not callable(getattr(tx, "interaction_context", None)):
                raise CommandRejected()
            tx.interaction_context(binding, command.class_id, command.term_id)
            payload = command.canonical()
            expected = fingerprint(payload)
            existing = tx.receipt(binding, key)
            if existing is not None:
                proposal = tx.proposal(binding["workspace_id"], existing["proposal_id"])
                if (proposal is None or proposal["payload"] != payload or proposal["payload_hash"] != expected
                        or proposal["actor_id"] != binding["actor_id"] or proposal["state"] != "committed"
                        or existing["receipt"].resource_id != command.thread_id):
                    raise CommandRejected()
                tx.require_interaction_commit(binding, key, expected, command)
                return CommandStatus(existing["proposal_id"], expected, "committed", existing["receipt"])
            marker = _title.set((id(self.store), binding["workspace_id"], binding["actor_id"], payload, title))
            try:
                self._validate(tx, binding, command, now)
                proposal = Proposal(uuid4(), expected, "W1", now + timedelta(minutes=10), command)
                tx.save_proposal(proposal, binding, payload, "manage-conversation")
                receipt = tx.apply(binding, command, now)
                tx.finish(binding, proposal.proposal_id, key, expected, receipt, now)
                return CommandStatus(proposal.proposal_id, expected, "committed", receipt)
            finally:
                _title.reset(marker)
        return self._run(credentials, "command.commit", save, class_id=command.class_id, term_id=command.term_id,
                         resource_id=command.thread_id)

    @staticmethod
    def decode_command(payload):
        if type(payload) is dict and payload.get("command") in {value.command for value in INTERACTIONS}:
            return decode_interaction(payload)
        return AdmissionGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        if type(command) in INTERACTIONS:
            return ControlDecision(level=Risk.W1, requires_approval=False, policy_version="d1-human-interaction.v1")
        return AdmissionGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        return "manage-conversation" if type(command) in INTERACTIONS else AdmissionGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if type(command) in INTERACTIONS:
            if not callable(getattr(tx, "validate_interaction", None)):
                raise CommandRejected()
            tx.validate_interaction(binding, command, now)
        elif tx.has_committed_admission(binding):
            super()._validate(tx, binding, command, now)
        else:
            ConversationExitBusinessGateway._validate(self, tx, binding, command, now)

    def enqueue(self, token, client, csrf, workspace_id, class_id, term_id, thread_id, request_id, text, mode, draft_kind="task"):
        # An explicit human send is W1 interaction persistence, not approval of
        # student facts. Metadata proposal, input, queue receipt and audit share
        # one BCG transaction. Raw input is never saved in proposal or audit.
        def save(tx, binding, now):
            if not callable(getattr(tx, "interaction_thread", None)):
                raise CommandRejected()
            row = tx.interaction_thread(binding, class_id, term_id, thread_id, now)
            try:
                scope = ConversationScope(binding["workspace_id"], binding["actor_id"], class_id, term_id, row["student_id"])
                intent = SendIntent(scope, thread_id, request_id, text, mode, draft_kind)
                command = EnqueueConversation.from_intent(intent)
            except ValueError:
                raise CommandRejected() from None
            key = send_receipt_key(scope, thread_id, request_id)
            existing = tx.interaction_replay(binding, command, key, intent)
            if existing is not None:
                return existing
            marker = _input.set((id(self.store), binding["workspace_id"], binding["actor_id"], intent))
            try:
                self._validate(tx, binding, command, now)
                payload = command.canonical()
                proposal = Proposal(uuid4(), fingerprint(payload), "W1", now + timedelta(minutes=10), command)
                tx.save_proposal(proposal, binding, payload, "manage-conversation")
                receipt = tx.apply(binding, command, now)
                tx.finish(binding, proposal.proposal_id, key, proposal.payload_hash, receipt, now)
                return CommandStatus(proposal.proposal_id, proposal.payload_hash, "committed", receipt)
            finally:
                _input.reset(marker)
        return self._run((token, client, csrf, workspace_id), "command.commit", save,
                         class_id=class_id, term_id=term_id, resource_id=thread_id)


class ConversationInteractionQuery(AdmissionQueryGateway):
    def conversation_capabilities(self, token, client, csrf, workspace_id):
        return self._run((token, client, csrf, workspace_id), "conversation.history",
            lambda tx, binding, now: tx.interaction_capabilities(binding, now))

    def conversation_page(self, token, client, csrf, workspace_id, class_id, term_id, thread_id, *, before_ordinal=None, expected_version=None):
        def read(tx, binding, now):
            if any(type(value) is not UUID for value in (class_id, term_id, thread_id)):
                raise CommandRejected()
            return tx.conversation_page(binding, class_id, term_id, thread_id,
                before_ordinal=before_ordinal, expected_version=expected_version)
        return self._run((token, client, csrf, workspace_id), "conversation.history", read,
                         class_id=class_id, term_id=term_id, resource_id=thread_id)

    def conversation_listing(self, token, client, csrf, workspace_id, class_id, term_id, *, snapshot=None, offset=0):
        return self._run((token, client, csrf, workspace_id), "conversation.history",
            lambda tx, binding, now: tx.interaction_list_page(binding, class_id, term_id, now, snapshot=snapshot, offset=offset),
            class_id=class_id, term_id=term_id)

    def conversations(self, token, client, csrf, workspace_id, class_id, term_id):
        def read(tx, binding, now):
            if not callable(getattr(tx, "interaction_list", None)):
                raise CommandRejected()
            return tx.interaction_list(binding, class_id, term_id, now)
        return self._run((token, client, csrf, workspace_id), "conversation.history",
            read, class_id=class_id, term_id=term_id)

    def turn_status(self, token, client, csrf, workspace_id, class_id, term_id, thread_id, request_id):
        def read(tx, binding, now):
            if not callable(getattr(tx, "interaction_status", None)):
                raise CommandRejected()
            return tx.interaction_status(binding, class_id, term_id, thread_id, request_id, now)
        return self._run((token, client, csrf, workspace_id), "conversation.history",
            read,
            class_id=class_id, term_id=term_id, resource_id=thread_id)
