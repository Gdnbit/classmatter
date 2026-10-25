"""Server orchestration BCG, never injected into Pydantic AI tools."""
from contextvars import ContextVar
from datetime import timedelta
from uuid import uuid4

from class_os.domain.conversation_worker import ClaimRun, FinishRun, CancelRun, ReconcileRun, ClaimedRun, decode_run
from class_os.domain.durable_conversation import ConversationRun, TERMINAL_STATES
from class_os.domain.exit_package import checksum
from class_os.domain.roster import Proposal, CommandStatus
from .conversation_interaction import ConversationInteractionGateway
from .conversation_control import ControlDecision
from .roster import CommandRejected, fingerprint
from class_os.domain.risk import Risk


WORKER_TYPES = (ClaimRun, FinishRun, CancelRun, ReconcileRun)
_operation = ContextVar("classmatter_server_run_operation", default=None)


def current_worker_operation(store, binding, command):
    value = _operation.get()
    if (type(command) not in WORKER_TYPES or type(value) is not tuple or len(value) != 6
            or value[:3] != (id(store), binding["workspace_id"], binding["actor_id"])
            or value[3] != command.canonical()):
        raise CommandRejected()
    return value[4], value[5]


class ConversationWorkerGateway(ConversationInteractionGateway):
    @staticmethod
    def audit_purpose(action):
        return "manage-conversation" if action.startswith("command.") else ConversationInteractionGateway.audit_purpose(action)

    @staticmethod
    def decode_command(payload):
        if type(payload) is dict and payload.get("command") in {value.command for value in WORKER_TYPES}:
            return decode_run(payload)
        return ConversationInteractionGateway.decode_command(payload)

    @staticmethod
    def assess_command(tx, binding, command):
        if type(command) in WORKER_TYPES:
            return ControlDecision(level=Risk.W1, requires_approval=False, policy_version="d1-run-lifecycle.v1")
        return ConversationInteractionGateway.assess_command(tx, binding, command)

    @staticmethod
    def command_purpose(command, payload):
        return "manage-conversation" if type(command) in WORKER_TYPES else ConversationInteractionGateway.command_purpose(command, payload)

    def _validate(self, tx, binding, command, now):
        if type(command) in WORKER_TYPES:
            if not callable(getattr(tx, "validate_worker", None)):
                raise CommandRejected()
            current_worker_operation(self.store, binding, command)
            tx.validate_worker(binding, command, now)
        else:
            super()._validate(tx, binding, command, now)

    def _perform(self, tx, binding, command, now, *, ticket=None, output=None):
        marker = _operation.set((id(self.store), binding["workspace_id"], binding["actor_id"], command.canonical(), ticket, output))
        try:
            self._validate(tx, binding, command, now)
            payload = command.canonical()
            proposal = Proposal(uuid4(), fingerprint(payload), "W1", now + timedelta(minutes=10), command)
            tx.save_proposal(proposal, binding, payload, "manage-conversation")
            receipt = tx.apply(binding, command, now)
            tx.finish(binding, proposal.proposal_id, uuid4(), proposal.payload_hash, receipt, now)
            return CommandStatus(proposal.proposal_id, proposal.payload_hash, "committed", receipt)
        finally:
            _operation.reset(marker)

    def claim(self, credentials, class_id, term_id, thread_id, request_id):
        private = []
        def start(tx, binding, now):
            if not callable(getattr(tx, "worker_row", None)):
                raise CommandRejected()
            row = tx.worker_row(binding, class_id, term_id, thread_id, now, request_id=request_id)
            if row["state"] != "queued":
                return None  # Never reissue a dispatch object after lost replies.
            try:
                if now >= row["queued_until"]:
                    return self._perform(tx, binding, ReconcileRun(thread_id, class_id, term_id, row["run_id"], row["version"]), now)
                intent = tx.worker_input(binding, class_id, term_id, thread_id, row)
                command = ClaimRun(thread_id, class_id, term_id, row["run_id"], row["version"], uuid4(), now + timedelta(minutes=1), intent.request_hash)
                result = self._perform(tx, binding, command, now)
                claimed = ConversationRun(command.run_id, "running", 2, command.generation, now, command.lease_until)
                private.append(ClaimedRun(intent.scope, row["turn_id"], intent, claimed))
                return result
            except ValueError:
                raise CommandRejected() from None
        self._run(credentials, "command.commit", start, class_id=class_id, term_id=term_id, resource_id=thread_id)
        # _run returns only after the original receipt and trusted audit COMMIT.
        return private[0] if private else None

    def finish_run(self, credentials, ticket, state, output=None, *, duration_ms=None, input_tokens=None, output_tokens=None):
        if type(ticket) is not ClaimedRun:
            raise CommandRejected()
        scope, thread = ticket.scope, ticket.intent.thread_id
        def finish(tx, binding, now):
            if scope.workspace_id != binding["workspace_id"] or scope.owner_id != binding["actor_id"] or not callable(getattr(tx, "worker_row", None)):
                raise CommandRejected()
            row = tx.worker_row(binding, scope.class_id, scope.term_id, thread, now, run_id=ticket.run.run_id)
            try:
                command = FinishRun(thread, scope.class_id, scope.term_id, ticket.run.run_id, row["version"], ticket.run.generation,
                    state, checksum(output) if output is not None else None, duration_ms, input_tokens, output_tokens)
            except ValueError:
                raise CommandRejected() from None
            return self._perform(tx, binding, command, now, ticket=ticket, output=output)
        return self._run(credentials, "command.commit", finish, class_id=scope.class_id, term_id=scope.term_id, resource_id=ticket.run.run_id)

    def cancel_run(self, credentials, class_id, term_id, thread_id, run_id, expected_version):
        def cancel(tx, binding, now):
            if not callable(getattr(tx, "worker_row", None)):
                raise CommandRejected()
            row = tx.worker_row(binding, class_id, term_id, thread_id, now, run_id=run_id, active=False)
            if row["state"] in TERMINAL_STATES or row["state"] == "cancel_requested":
                return None
            try:
                command = CancelRun(thread_id, class_id, term_id, run_id, expected_version)
            except ValueError:
                raise CommandRejected() from None
            return self._perform(tx, binding, command, now)
        return self._run(credentials, "command.commit", cancel, class_id=class_id, term_id=term_id, resource_id=run_id)

    def reconcile_run(self, credentials, class_id, term_id, thread_id, run_id):
        def reconcile(tx, binding, now):
            if not callable(getattr(tx, "worker_row", None)):
                raise CommandRejected()
            row = tx.worker_row(binding, class_id, term_id, thread_id, now, run_id=run_id, active=False)
            if row["state"] in TERMINAL_STATES or now < (row["queued_until"] if row["state"] == "queued" else row["lease_until"]):
                return None
            try:
                command = ReconcileRun(thread_id, class_id, term_id, run_id, row["version"])
            except ValueError:
                raise CommandRejected() from None
            return self._perform(tx, binding, command, now)
        return self._run(credentials, "command.commit", reconcile, class_id=class_id, term_id=term_id, resource_id=run_id)
