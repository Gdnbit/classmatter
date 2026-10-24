"""Synthetic R1 BCG/QG. Only these boundaries receive business repositories."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

import rfc8785

from class_os.application.identity import IdentityDenied, digest
from class_os.application.audit import AuditUnavailable, require_audit
from class_os.domain.risk import Assessment, Command, evaluate
from class_os.domain.roster import CreateClass, CreateStudent, Proposal, Receipt, CommandStatus, TermMetadata, decode
from .activity import validate_activity, decision
from class_os.domain.exit_package import CreateExitExport, ExitSummary, ExitArtifact
from class_os.domain.query_snapshot import WorkSnapshot
from class_os.domain.model_control import ModelControl


class CommandRejected(Exception):
    def __init__(self):
        super().__init__("Business request rejected")


def fingerprint(payload):
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


class GatewayBase:
    @staticmethod
    def audit_purpose(action):
        if action.startswith("model."):
            return "manage-model"
        if action in ("activity.today", "student.timeline", "audit.list"):
            return "manage-class"
        return "exit-recovery" if action.startswith("exit.") else "manage-roster"

    def __init__(self, identity, store, *, clock=lambda: datetime.now(timezone.utc)):
        self.identity, self.store, self.clock = identity, store, clock

    def _run(self, credentials, action, callback, *, proposal_id=None, class_id=None, term_id=None, resource_id=None):
        token, client, csrf, workspace_id = credentials
        if not csrf or type(workspace_id) is not UUID:
            raise IdentityDenied()
        with self.identity.authorized_session(token, client, workspace_id, csrf) as subject:
            return self._authorized_run(subject, client, csrf, action, callback, proposal_id=proposal_id,
                                        class_id=class_id, term_id=term_id, resource_id=resource_id)

    def _authorized_run(self, subject, client, csrf, action, callback, *, proposal_id, class_id, term_id, resource_id):
        binding = {"workspace_id": subject.workspace_id, "actor_id": subject.owner_id,
                   "session_digest": subject.session_id, "client_digest": digest(client), "csrf_digest": digest(csrf)}
        denied, result = False, None
        with self.store.atomic() as tx:
            # Timestamp/expiry evaluation after acquiring the business lock:
            # waiting for another commit must not make an old as_of look current.
            now = self.clock()
            if now.tzinfo is None or now.utcoffset() != timedelta(0):
                raise RuntimeError("Business clock must be UTC")
            identity_expired = now >= subject.expires_at
            try:
                if identity_expired or not tx.synthetic_workspace(subject.workspace_id):
                    raise CommandRejected()
                result = callback(tx, binding, now)
            except CommandRejected:
                denied = True
            reference = result.proposal_id if type(result) in (Proposal, CommandStatus) else proposal_id
            reference = reference if type(reference) is UUID else None
            class_id = class_id if type(class_id) is UUID else None
            term_id = term_id if type(term_id) is UUID else None
            metadata = {"proposal_id": reference, "payload_hash": None, "receipt_id": None,
                        "resource_id": resource_id if type(resource_id) is UUID else class_id,
                        "resource_version": None, "class_id": class_id, "term_id": term_id,
                        "purpose": self.audit_purpose(action)}
            if reference is not None and not identity_expired:
                stored = tx.proposal(subject.workspace_id, reference)
                if stored and stored["actor_id"] == subject.owner_id:
                    metadata["payload_hash"] = stored["payload_hash"]
                    payload = stored["payload"]
                    for field in ("class_id", "term_id"):
                        if metadata[field] is None:
                            try:
                                metadata[field] = UUID(payload[field])
                            except (KeyError, TypeError, ValueError):
                                pass  # Do not invent scope for legacy/corrupt proposals.
                    metadata["purpose"] = stored["purpose"]
            if type(result) is Receipt:
                metadata.update(receipt_id=result.receipt_id, resource_id=result.resource_id, resource_version=result.version)
            if type(result) is TermMetadata:
                metadata.update(resource_id=result.term_id, resource_version=result.version)
            if type(result) is CommandStatus and result.receipt:
                metadata.update(receipt_id=result.receipt.receipt_id, resource_id=result.receipt.resource_id, resource_version=result.receipt.version)
            if type(result) is ExitSummary:
                metadata["payload_hash"] = result.core_hash
            if type(result) is ExitArtifact:
                metadata.update(payload_hash=result.package_hash, resource_id=result.export_id)
            if type(result) is WorkSnapshot:
                metadata.update(payload_hash=result.source_hash,
                                resource_version=result.student_version if result.student_id else result.class_version,
                                purpose="manage-class")
                if result.student_id is not None:
                    metadata["resource_id"] = result.student_id
            audit_id = require_audit(tx.audit, binding, action, "denied" if denied else "allowed", now, metadata)
            if type(result) is WorkSnapshot:
                result = replace(result, audit_id=audit_id)
        if identity_expired:
            raise IdentityDenied()
        if denied:
            raise CommandRejected()
        return result


class BusinessGateway(GatewayBase):
    """Registered commands only. Never injected into Agent/Tool adapters."""

    decode_command = staticmethod(decode)
    assess_command = staticmethod(decision)

    @staticmethod
    def command_purpose(command, payload):
        if type(command) is ModelControl:
            return "manage-model"
        return "exit-recovery" if type(command) is CreateExitExport else "manage-class" if payload["command"].startswith(("record.", "task.")) else "manage-roster"

    @staticmethod
    def _validate(tx, binding, command, now):
        if type(command) is ModelControl:
            if not tx.validate_model_configuration(binding, command):
                raise CommandRejected()
        elif type(command) is CreateExitExport:
            if tx.export_exists(binding["workspace_id"], command.export_id) or tx.exit_summary(binding["workspace_id"]).core_hash != command.expected_core_hash:
                raise CommandRejected()
        elif type(command) is CreateClass:
            if tx.current_class(binding["workspace_id"]):
                raise CommandRejected()
        elif type(command) is CreateStudent:
            current = tx.class_context(binding["workspace_id"], command.class_id, command.term_id)
            if (not current or current["status"] != "active" or current["term_status"] != "active"
                    or current["version"] != command.expected_class_version
                    or tx.student_exists(binding["workspace_id"], command.student_id)):
                raise CommandRejected()
        elif not validate_activity(tx, binding, command, now):
            raise CommandRejected()

    def preview(self, token, client, csrf, workspace_id, command):
        def preview(tx, binding, now):
            self._validate(tx, binding, command, now)
            payload = command.canonical()
            assessed = self.assess_command(tx, binding, command)
            if not assessed.admitted:
                raise CommandRejected()
            result = Proposal(uuid4(), fingerprint(payload), assessed.level.name, now + timedelta(minutes=10), command)
            tx.save_proposal(result, binding, payload, self.command_purpose(command, payload))
            return result
        return self._run((token, client, csrf, workspace_id), "command.preview", preview)

    @staticmethod
    def _proposal(tx, binding, proposal_id, now):
        if type(proposal_id) is not UUID:
            raise CommandRejected()
        proposal = tx.proposal(binding["workspace_id"], proposal_id)
        if (not proposal or proposal["state"] in ("rejected", "committed") or now >= proposal["expires_at"]
                or any(proposal[key] != value for key, value in binding.items())
                or fingerprint(proposal["payload"]) != proposal["payload_hash"]):
            raise CommandRejected()
        return proposal

    def approve(self, token, client, csrf, workspace_id, proposal_id, expected_hash):
        # Called only by the private human-approval adapter, never a Tool. HTTP
        # Origin/CSRF validation remains mandatory when an HTTP adapter is wired.
        def approve(tx, binding, now):
            proposal = self._proposal(tx, binding, proposal_id, now)
            if not isinstance(expected_hash, str) or not hmac.compare_digest(proposal["payload_hash"], expected_hash):
                raise CommandRejected()
            command = self.decode_command(proposal["payload"])
            self._validate(tx, binding, command, now)
            assessed = self.assess_command(tx, binding, command)
            if not assessed.admitted or not assessed.requires_approval:
                raise CommandRejected()
            secret = secrets.token_urlsafe(32)
            tx.approve(proposal_id, digest(secret), now)
            return secret
        return self._run((token, client, csrf, workspace_id), "command.approve", approve, proposal_id=proposal_id)

    def reject(self, token, client, csrf, workspace_id, proposal_id):
        def reject(tx, binding, now):
            self._proposal(tx, binding, proposal_id, now)
            tx.reject(proposal_id, now)
        return self._run((token, client, csrf, workspace_id), "command.reject", reject, proposal_id=proposal_id)

    def commit(self, token, client, csrf, workspace_id, proposal_id, idempotency_key, approval=None):
        def commit(tx, binding, now):
            if type(idempotency_key) is not UUID or type(proposal_id) is not UUID:
                raise CommandRejected()
            # Check persisted receipt first: response loss must not perform the
            # mutation again, even after proposal consumption/expiry.
            existing = tx.receipt(binding, idempotency_key)
            if existing:
                if existing["proposal_id"] != proposal_id:
                    raise CommandRejected()
                return existing["receipt"]
            proposal = self._proposal(tx, binding, proposal_id, now)
            command = self.decode_command(proposal["payload"])
            self._validate(tx, binding, command, now)
            assessed = self.assess_command(tx, binding, command)
            if not assessed.admitted:
                raise CommandRejected()
            if assessed.requires_approval:
                proof = tx.approval(proposal_id)
                if (proposal["state"] != "approved" or not proof or proof["consumed_at"] is not None
                        or not isinstance(approval, str) or not 32 <= len(approval) <= 128
                        or not hmac.compare_digest(proof["nonce_digest"], digest(approval))):
                    raise CommandRejected()
            result = tx.apply(binding, command, now)
            tx.finish(binding, proposal_id, idempotency_key, proposal["payload_hash"], result, now)
            return result
        return self._run((token, client, csrf, workspace_id), "command.commit", commit, proposal_id=proposal_id)


class QueryGateway(GatewayBase):
    def term_metadata(self, token, client, csrf, workspace_id, class_id, term_id):
        def query(tx, binding, now):
            if any(type(value) is not UUID for value in (class_id, term_id)):
                raise CommandRejected()
            current = tx.term_metadata(binding["workspace_id"], class_id, term_id)
            if current is None:
                raise CommandRejected()
            return current
        return self._run((token, client, csrf, workspace_id), "class.context", query,
                         class_id=class_id, term_id=term_id, resource_id=term_id)

    def model_configuration(self, credentials, *, action="model.config.read"):
        if action not in ("model.config.read", "model.test.started", "model.test.completed", "model.test.failed", "model.enable", "model.disable", "model.invoke"):
            raise CommandRejected()
        return self._run(credentials, action, lambda tx, binding, now: tx.model_configuration(binding["workspace_id"]))

    def command_status(self, token, client, csrf, workspace_id, proposal_id, key):
        def query(tx, binding, now):
            if type(proposal_id) is not UUID or type(key) is not UUID:
                raise CommandRejected()
            proposal = tx.proposal(binding["workspace_id"], proposal_id)
            if not proposal or proposal["actor_id"] != binding["actor_id"] or fingerprint(proposal["payload"]) != proposal["payload_hash"]:
                raise CommandRejected()
            receipt = tx.receipt(binding, key)
            if receipt and receipt["proposal_id"] != proposal_id:
                raise CommandRejected()
            status = "committed" if receipt else "unavailable" if proposal["state"] in ("committed", "rejected") or now >= proposal["expires_at"] else "not_committed"
            return CommandStatus(proposal_id, proposal["payload_hash"], status, receipt["receipt"] if receipt else None)
        return self._run((token, client, csrf, workspace_id), "command.status", query, proposal_id=proposal_id)

    def student_scope(self, token, client, csrf, workspace_id, class_id, term_id, student_id):
        def query(tx, binding, now):
            if any(type(value) is not UUID for value in (class_id, term_id, student_id)):
                raise CommandRejected()
            context = tx.class_context(binding["workspace_id"], class_id, term_id)
            if (not context or context["status"] != "active" or context["term_status"] != "active"
                    or not tx.active_student(binding["workspace_id"], class_id, term_id, student_id, now)):
                raise CommandRejected()
        return self._run((token, client, csrf, workspace_id), "student.timeline", query,
                         class_id=class_id, term_id=term_id, resource_id=student_id)

    def work_snapshot(self, token, client, csrf, workspace_id, class_id, term_id, *, student_id=None):
        def query(tx, binding, now):
            if type(class_id) is not UUID or type(term_id) is not UUID:
                raise CommandRejected()
            context = tx.class_context(binding["workspace_id"], class_id, term_id)
            if not context or context["status"] != "active" or context["term_status"] != "active":
                raise CommandRejected()
            selected = None
            if student_id is not None:
                if type(student_id) is not UUID:
                    raise CommandRejected()
                selected = tx.active_student(binding["workspace_id"], class_id, term_id, student_id, now)
                if not selected:
                    raise CommandRejected()
            projection = tx.activity(binding["workspace_id"], class_id, term_id, now, student_id=student_id)
            latest = {}
            for row in projection["records"]:
                if row["record_id"] not in latest:
                    latest[row["record_id"]] = row
            tasks = projection["tasks"]
            sources = {"workspace_id": str(binding["workspace_id"]), "purpose": "read-current-work", "rule_version": "r1.0",
                       "class_id": str(class_id), "term_id": str(term_id), "class_version": context["version"],
                       "as_of": now.isoformat(),
                       "records": sorted((str(row["record_id"]), row["version"]) for row in latest.values()),
                       "tasks": sorted((str(row["task_id"]), row["version"]) for row in tasks)}
            if selected:
                sources.update(rule_version="student-current-work.v1",
                               student_scope={"id": str(student_id), "version": selected["version"]})
            return WorkSnapshot(class_id, term_id, context["version"], now,
                                sum(row["status"] not in ("done", "cancelled") for row in tasks),
                                sum(row["status"] == "waiting" for row in tasks), len(latest), fingerprint(sources),
                                student_id=student_id, student_version=selected["version"] if selected else None)
        return self._run((token, client, csrf, workspace_id), "activity.today", query, class_id=class_id, term_id=term_id,
                         resource_id=student_id or class_id)

    def exit_summary(self, token, client, csrf, workspace_id):
        return self._run((token, client, csrf, workspace_id), "exit.summary",
                         lambda tx, binding, now: tx.exit_summary(binding["workspace_id"]))

    def exit_download(self, token, client, csrf, workspace_id, export_id):
        def query(tx, binding, now):
            if type(export_id) is not UUID:
                raise CommandRejected()
            artifact = tx.exit_artifact(binding, export_id, now)
            if artifact is None:
                raise CommandRejected()
            return artifact
        return self._run((token, client, csrf, workspace_id), "exit.download", query, resource_id=export_id)

    def agent_audit(self, credentials, run_id, status, class_id, term_id, *, student_id=None):
        if type(run_id) is not UUID or status not in ("started", "completed", "failed", "cancelled"):
            raise CommandRejected()
        def query(tx, binding, now):
            if status in ("started", "completed"):
                if any(type(value) is not UUID for value in (class_id, term_id)):
                    raise CommandRejected()
                context = tx.class_context(binding["workspace_id"], class_id, term_id)
                if not context or context["status"] != "active" or context["term_status"] != "active":
                    raise CommandRejected()
            if student_id is not None:
                if type(student_id) is not UUID:
                    raise CommandRejected()
                if status in ("started", "completed") and not tx.active_student(binding["workspace_id"], class_id, term_id, student_id, now):
                    raise CommandRejected()
        self._run(credentials, "agent.run." + status, query,
                  class_id=class_id, term_id=term_id, resource_id=run_id)

    def history(self, token, client, csrf, workspace_id):
        return self._run((token, client, csrf, workspace_id), "class.history",
                         lambda tx, binding, now: tx.class_history(binding["workspace_id"]))

    def projection(self, token, client, csrf, workspace_id, class_id, term_id, *, view="activity", student_id=None):
        if view not in ("activity", "identifiers", "duplicates"):
            raise CommandRejected()
        action = "student.timeline" if student_id else {"activity": "activity.today", "identifiers": "identifier.list", "duplicates": "duplicate.list"}[view]
        def query(tx, binding, now):
            if type(class_id) is not UUID or type(term_id) is not UUID or not tx.class_context(binding["workspace_id"], class_id, term_id):
                raise CommandRejected()
            if student_id is not None and (type(student_id) is not UUID or not tx.student_exists(binding["workspace_id"], student_id)):
                raise CommandRejected()
            if view == "identifiers":
                return tx.identifier_list(binding["workspace_id"], class_id, term_id)
            if view == "duplicates":
                return tx.duplicate_list(binding["workspace_id"], class_id, term_id, now)
            return tx.activity(binding["workspace_id"], class_id, term_id, now, student_id=student_id)
        return self._run((token, client, csrf, workspace_id), action, query, class_id=class_id, term_id=term_id)

    def audit_log(self, token, client, csrf, workspace_id, class_id, term_id):
        def query(tx, binding, now):
            if type(class_id) is not UUID or type(term_id) is not UUID or not tx.class_context(binding["workspace_id"], class_id, term_id):
                raise CommandRejected()
            rows = tx.audit_log(binding, class_id, term_id)
            return {"as_of": now, "entries": rows[:100], "truncated": len(rows) > 100, "partial_history": True}
        return self._run((token, client, csrf, workspace_id), "audit.list", query, class_id=class_id, term_id=term_id)

    def context(self, token, client, csrf, workspace_id):
        def query(tx, binding, now):
            return tx.current_context(binding["workspace_id"])
        return self._run((token, client, csrf, workspace_id), "class.context", query)

    def roster(self, token, client, csrf, workspace_id, class_id, term_id):
        def query(tx, binding, now):
            if type(class_id) is not UUID or type(term_id) is not UUID:
                raise CommandRejected()
            if not tx.class_context(binding["workspace_id"], class_id, term_id):
                raise CommandRejected()
            return tx.roster(binding["workspace_id"], class_id, term_id, now)
        return self._run((token, client, csrf, workspace_id), "roster.list", query, class_id=class_id, term_id=term_id)
