"""Oracle characterisation for the first T-REVAL-003 security runner slice."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "evals/class-os-v1/runners/security.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("class_os_security_eval", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTarget:
    """Only exercises oracle sensitivity; never a machine-green production target."""

    def __init__(self, *, leak=False, missing_audit=False, release_on_audit_failure=False,
                 approval_tool=False, replay_consumes=False, risk_downgrade=False,
                 generic_error=False, leak_log=False, leak_audit=False, mixed_denial=False,
                 leak_term=False, risk_combo_downgrade=False, malformed_approval=False,
                 rejected_replay_consumes=False, ignores_policy_version=False,
                 leak_resource_id=False, delete_downgrade=False, disguised_approval=False,
                 disguised_metadata_lies=False, receipt_minted=False,
                 approval_state_changed=False, hidden_business_write=False,
                 ui_only_auth=False, provider_before_audit=False,
                 export_artifact_on_fault=False, export_release_on_fault=False,
                 audit_query_bypass=False, omit_query_receipt=False,
                 audit_query_fault_leak=False):
        self.leak = leak
        self.missing_audit = missing_audit
        self.release_on_audit_failure = release_on_audit_failure
        self.approval_tool = approval_tool
        self.replay_consumes = replay_consumes
        self.risk_downgrade = risk_downgrade
        self.generic_error = generic_error
        self.leak_log = leak_log
        self.leak_audit = leak_audit
        self.mixed_denial = mixed_denial
        self.leak_term = leak_term
        self.risk_combo_downgrade = risk_combo_downgrade
        self.malformed_approval = malformed_approval
        self.rejected_replay_consumes = rejected_replay_consumes
        self.ignores_policy_version = ignores_policy_version
        self.leak_resource_id = leak_resource_id
        self.delete_downgrade = delete_downgrade
        self.disguised_approval = disguised_approval
        self.disguised_metadata_lies = disguised_metadata_lies
        self.receipt_minted = receipt_minted
        self.approval_state_changed = approval_state_changed
        self.hidden_business_write = hidden_business_write
        self.ui_only_auth = ui_only_auth
        self.provider_before_audit = provider_before_audit
        self.export_artifact_on_fault = export_artifact_on_fault
        self.export_release_on_fault = export_release_on_fault
        self.audit_query_bypass = audit_query_bypass
        self.omit_query_receipt = omit_query_receipt
        self.audit_query_fault_leak = audit_query_fault_leak
        self.data = None

    def prepare(self, fixture):
        self.data = fixture
        self.approval_consumptions = 0
        self.audit_query_receipt_count = 0

    def request(self, *, surface, operation, actor_id, workspace_id, resource_id,
                audit_fault=False):
        if audit_fault:
            return {
                "status": 200 if self.release_on_audit_failure else 503,
                "error_code": None if self.release_on_audit_failure else "AUDIT_UNAVAILABLE",
                "response": (resource_id if self.leak_resource_id else
                             "SENSITIVE_CANARY" if self.release_on_audit_failure else
                             '{"error":"AUDIT_UNAVAILABLE"}' if self.generic_error else ""),
                "logs": "SENSITIVE_CANARY" if self.leak_log else "", "trace": "",
                "audit": [{"action": "audit.failed", "payload": "SENSITIVE_CANARY"}] if self.leak_audit else [],
                "provider_calls": 1 if self.release_on_audit_failure or (
                    self.provider_before_audit and surface == "model-projection"
                ) else 0,
                "business_writes": 0,
                "security_signal": {"kind": "audit-unavailable", "contains_business_content": False},
            }
        return {
            "status": 200 if self.leak or (
                self.ui_only_auth and actor_id == "synthetic-unprivileged-actor" and surface != "ui-api"
            ) else 403 if self.mixed_denial and surface == "rest" else 404,
            "error_code": None if self.leak or (
                self.ui_only_auth and actor_id == "synthetic-unprivileged-actor" and surface != "ui-api"
            ) else "FORBIDDEN" if self.mixed_denial and surface == "rest" else "NOT_FOUND_SAFE",
            "response": ("WORKSPACE_B_CANARY" if self.leak else
                         "SENSITIVE_D2_NAME_CANARY" if self.ui_only_auth and
                         actor_id == "synthetic-unprivileged-actor" and surface != "ui-api" else
                         next(row["term_id"] for row in self.data["data"]["students"]
                              if row["display_name"] == "WORKSPACE_B_CANARY") if self.leak_term else ""),
            "logs": "", "trace": "",
            "audit": [] if self.missing_audit else [{"action": "access.denied", "data_included": False}],
            "provider_calls": 0, "business_writes": 0,
            "security_signal": {"kind": "none", "contains_business_content": False},
        }

    def cleanup(self):
        self.data = None
        self.audit_query_receipt_count = 0

    def audit_query_cleanup_state(self):
        return {"namespace_present": self.data is not None,
                "audit_events": len(self.data["data"].get("audit_events", [])) if self.data else 0,
                "query_receipts": self.audit_query_receipt_count,
                "cached_results": 0}

    def catalogs(self):
        def descriptor(capability_id, *, operation_family="query", side_effect="none",
                       risk_floor="Q", approval_effect="none"):
            return {"capability_id": capability_id, "operation_family": operation_family,
                    "side_effect": side_effect, "risk_floor": risk_floor,
                    "proposal_effect": "none", "approval_effect": approval_effect,
                    "receipt_effect": "none", "schema_sha256": "a" * 64}
        tools = [descriptor("student.search"), descriptor("attention.list")]
        if self.approval_tool:
            tools.append(descriptor("approval.approve", operation_family="approval",
                                    side_effect="business-write", risk_floor="W2",
                                    approval_effect="consume"))
        if self.disguised_approval or self.disguised_metadata_lies:
            tools.append(
                descriptor("consent.confirm") if self.disguised_metadata_lies else
                descriptor("consent.confirm", operation_family="approval",
                           side_effect="business-write", risk_floor="W2", approval_effect="consume")
            )
        return {"tool": tools,
                "skill": [descriptor("record-review", operation_family="draft",
                                     side_effect="ephemeral-draft", risk_floor="D")],
                "mcp": [descriptor("roster.lookup")]}

    def runtime_model_capabilities(self):
        # Independent synthetic handler inventory; do not derive this from the visible catalog.
        return ["student.search", "attention.list", "record-review", "roster.lookup"]

    def export_entrypoints(self):
        return ["export-api", "export-worker", "export-download"]

    def runtime_export_entrypoints(self):
        return ["export-api", "export-worker", "export-download"]

    def export_cleanup_state(self):
        return {"available_objects": 0, "active_links": 0,
                "canary_present": False, "residual_sha256": None}

    def export_attempt(self, *, surface, fault_stage, fixture, audit_fault=True):
        payload = fixture["data"]["export"]
        if not audit_fault:
            writes = 0 if surface == "export-download" else 1
            return {
                "status": 200, "error_code": None, "response": '{"export":"ready"}',
                "logs": "", "trace": "",
                "audit": [{"action": "export.release", "durable": True,
                           "before_release": True, "payload_included": False}],
                "artifact_created": 1, "artifact_released": 1,
                "temp_objects_available": 0,
                "download_bytes": payload["payload_byte_count"], "active_links": 1,
                "provider_calls": 0, "business_writes": writes,
                "bcg_commands": writes, "direct_repository_writes": 0,
                "artifact_sha256": payload["payload_sha256"],
                "download_sha256": payload["payload_sha256"],
                "security_signal": {"kind": "none", "contains_business_content": False},
            }
        writes = int(fault_stage in ("publish", "release") and surface != "export-download")
        return {
            "status": 503, "error_code": "AUDIT_UNAVAILABLE", "response": "",
            "logs": "", "trace": "", "audit": [],
            "artifact_created": int(self.export_artifact_on_fault),
            "artifact_released": int(self.export_release_on_fault),
            "temp_objects_available": 0, "download_bytes": 1 if self.export_release_on_fault else 0,
            "active_links": int(self.export_release_on_fault),
            "provider_calls": 0, "business_writes": writes,
            "bcg_commands": writes, "direct_repository_writes": 0,
            "artifact_sha256": None, "download_sha256": None,
            "security_signal": {"kind": "audit-unavailable", "contains_business_content": False},
        }

    def observe_export(self, *, surface, fault_stage, export_id, request_id):
        # Synthetic independent observer. Production must inspect audit store,
        # object/index store, and egress without consulting export_attempt output.
        payload = self.data["data"]["export"]
        assert payload["export_id"] == export_id and payload["request_id"] == request_id
        success = fault_stage == "none"
        writes = int(surface != "export-download" and
                     (success or fault_stage in ("publish", "release")))
        return {
            "request_id": request_id, "export_id": export_id,
            "audit_receipt": {
                "action": "export.release", "request_id": request_id,
                "export_id": export_id, "payload_sha256": payload["payload_sha256"],
                "payload_included": False,
            } if success else None,
            "bcg_receipt_count": writes,
            "audit_commit_sequence": 1 if success else 0,
            "artifact_publish_sequence": 2 if success else 0,
            "link_activation_sequence": 3 if success else 0,
            "download_release_sequence": 4 if success else 0,
            "object_count": int(success), "index_count": int(success),
            "egress_bytes": payload["payload_byte_count"] if success else 0,
            "object_sha256": payload["payload_sha256"] if success else None,
            "egress_sha256": payload["payload_sha256"] if success else None,
            "canary_present": success,
            "failed_job_metadata_count": writes if not success else 0,
            "metadata_contains_business_content": False,
        }

    def audit_query_entrypoints(self):
        return ["ui-api", "rest"]

    def runtime_audit_query_entrypoints(self):
        return ["ui-api", "rest"]

    @staticmethod
    def _audit_query_authorized(fixture, context):
        clock = fixture["meta"]["clock"]
        session = next((row for row in fixture["data"]["audit_query_sessions"]
                        if row["session_id"] == context["session_id"] and
                        row["actor_id"] == context["actor_id"]), None)
        grant = next((row for row in fixture["data"]["audit_query_grants"]
                      if row["grant_id"] == context["grant_id"] and
                      row["actor_id"] == context["actor_id"] and
                      row["workspace_id"] == context["target_workspace_id"] and
                      row["action"] == context["action"]), None)
        return bool(session and not session["revoked"] and session["expires_at"] > clock
                    and grant and not grant["revoked"] and grant["expires_at"] > clock)

    def audit_query_attempt(self, *, surface, fixture, request_context):
        actor = request_context["actor_id"]
        workspace = request_context["target_workspace_id"]
        authorized = self._audit_query_authorized(fixture, request_context) or (
            self.audit_query_bypass and not fixture["data"]["audit_query_grants"]
        )
        fault = request_context["audit_fault"]
        receipt = {"action": "audit.query", "actor_id": actor, "workspace_id": workspace,
                   "request_id": request_context["request_id"],
                   "query_scope_hash": request_context["query_scope_hash"],
                   "occurred_at": request_context["occurred_at"],
                   "result_count": request_context["result_count"],
                   "payload_included": False}
        return {
            "status": 200 if (fault and self.audit_query_fault_leak) else 503 if fault
                      else 200 if authorized else 403,
            "error_code": None if (fault and self.audit_query_fault_leak) else "AUDIT_UNAVAILABLE" if fault
                          else None if authorized else "FORBIDDEN",
            "response": '{"count":1}' if (fault and self.audit_query_fault_leak) or (authorized and not fault)
                        else "",
            "logs": "", "trace": "", "provider_calls": 0, "business_writes": 0,
            "audit_receipts": [] if self.omit_query_receipt or not authorized or fault else [receipt],
            "security_signal": {"kind": "audit-unavailable" if fault else "none",
                                "contains_business_content": False},
        }

    def observe_audit_query(self, *, surface, request_context):
        if (not self._audit_query_authorized(self.data, request_context)
                or request_context["audit_fault"]):
            return {"persisted_receipts": 0, "receipt": None,
                    "audit_commit_sequence": 0, "response_release_sequence": 1}
        # This fake is only oracle characterisation. A production observer must read the
        # durable audit store and response egress independently of the audited service.
        self.audit_query_receipt_count += 1
        query_scope = {key: request_context[key] for key in (
            "actor_id", "session_id", "target_workspace_id", "grant_id",
            "surface", "action", "filter",
        )}
        import hashlib
        query_hash = hashlib.sha256(json.dumps(
            query_scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        return {"persisted_receipts": 1,
                "receipt": {"action": "audit.query", "actor_id": request_context["actor_id"],
                            "workspace_id": request_context["target_workspace_id"],
                            "request_id": request_context["request_id"],
                            "query_scope_hash": query_hash,
                            "occurred_at": self.data["meta"]["clock"],
                            "result_count": 1, "payload_included": False},
                "audit_commit_sequence": 1, "response_release_sequence": 2}

    def agent_tool_attempt(self, name):
        if (self.disguised_approval or self.disguised_metadata_lies) and name == "consent.confirm":
            return {"status": "allowed", "proposal_consumed": not (
                        self.receipt_minted or self.approval_state_changed),
                    "approval_state_changes": int(self.approval_state_changed),
                    "approval_receipts_minted": int(self.receipt_minted),
                    "business_writes": int(self.hidden_business_write),
                    "audit_action": "tool.allowed" if (
                        self.receipt_minted or self.approval_state_changed or self.hidden_business_write
                    )
                    else "approval.consumed"}
        return {"status": "forbidden", "proposal_consumed": False,
                "approval_state_changes": 0, "approval_receipts_minted": 0,
                "business_writes": 0,
                "audit_action": "tool.denied"}

    def approval_attempt(self, variant, fixture):
        success = variant == "matching-trusted-ui-first"
        if self.replay_consumes and variant == "duplicate-click":
            success = True
        if self.rejected_replay_consumes and variant == "rejected-replay":
            success = True
        if success:
            self.approval_consumptions += 1
        return {
            "accepted": success,
            "consumption_count": True if success and self.malformed_approval else 1 if success else 0,
            "total_consumptions": self.approval_consumptions,
            "business_writes": 1 if success else 0,
            "proposal_id": fixture["data"]["proposals"][0]["proposal_id"],
            "receipt_id": fixture["data"]["approval_requests"][0]["approval_request_id"],
            "audit_action": "approval.consumed" if success else "approval.denied",
        }

    def evaluate_risk(self, command):
        if command["risk_policy_version"] != "r1.0" and not self.ignores_policy_version:
            return {"decision": "reject", "risk": "UNCLASSIFIED",
                    "requires_recent_reauth": False, "policy_version": None,
                    "policy_sha256": None}
        floors = {"class.create": "W2", "student.create": "W1", "record.create": "W1",
                  "record.correct": "W2", "task.create": "W1", "exit_export.create": "W2"}
        forbidden_command = command["command"] in ("record.delete", "student.delete", "message.send")
        wrong_object = command["object_type"] != command["command"].split(".")[0]
        if forbidden_command or wrong_object or command["external"] or command["irreversible"]:
            decision, risk = "reject", "X"
        elif command["data_class"] == "D4" or command["attachment"]:
            decision = "reject"
            risk = "W2"
        elif (command["kind"] in ("discipline", "talk") or command["data_class"] == "D3"
              or command["affected_count"] > 1 or floors.get(command["command"]) == "W2"):
            decision, risk = "allow", "W2"
        else:
            decision, risk = "allow", "W1"
        if self.delete_downgrade and command["command"] == "record.delete":
            decision, risk = "allow", "W1"
        if self.risk_downgrade and command["data_class"] == "D3":
            risk = "W1"
        if self.risk_combo_downgrade and command["data_class"] == "D3" and command["affected_count"] > 1:
            risk = "W1"
        return {"decision": decision, "risk": risk,
                "requires_recent_reauth": (forbidden_command or wrong_object or command["external"]
                                           or command["irreversible"]),
                "policy_version": "r1.0",
                "policy_sha256": "1b7aec7579f20fd79e5b54a1e4cacab7ef5200e0cae7577db297328a3bd892ef"}


class SecurityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()

    def test_workspace_oracle_passes_only_isolated_minimally_audited_attempts(self):
        cases = self.runner.run_selected(FakeTarget(), ids={"E-AUTH-001"}, root=ROOT)
        self.assertEqual(["E-AUTH-001"], [case["eval_id"] for case in cases])
        self.assertEqual("passed", cases[0]["status"])
        self.assertEqual(4, cases[0]["attempt_count"])

    def test_workspace_leak_and_missing_denial_audit_are_caught(self):
        for target in (FakeTarget(leak=True), FakeTarget(missing_audit=True)):
            with self.subTest(target=vars(target)):
                case = self.runner.run_selected(target, ids={"E-AUTH-001"}, root=ROOT)[0]
                self.assertEqual("failed", case["status"])

    def test_audit_outage_cannot_release_data_or_call_provider(self):
        good = self.runner.run_selected(FakeTarget(), ids={"E-AUD-001"}, root=ROOT)[0]
        bad = self.runner.run_selected(
            FakeTarget(release_on_audit_failure=True), ids={"E-AUD-001"}, root=ROOT
        )[0]
        self.assertEqual("passed", good["status"])
        self.assertEqual("failed", bad["status"])
        self.assertEqual(15, good["attempt_count"])
        self.assertEqual(
            "passed",
            self.runner.run_selected(FakeTarget(generic_error=True), ids={"E-AUD-001"}, root=ROOT)[0]["status"],
        )
        for target in (FakeTarget(leak_log=True), FakeTarget(leak_audit=True),
                       FakeTarget(leak_resource_id=True)):
            self.assertEqual("failed", self.runner.run_selected(target, ids={"E-AUD-001"}, root=ROOT)[0]["status"])

    def test_workspace_foreign_field_and_mixed_error_are_caught(self):
        for target in (FakeTarget(leak_term=True), FakeTarget(mixed_denial=True)):
            self.assertEqual("failed", self.runner.run_selected(target, ids={"E-AUTH-001"}, root=ROOT)[0]["status"])

    def test_hidden_ui_does_not_authorize_direct_server_surfaces(self):
        good = self.runner.run_selected(FakeTarget(), ids={"E-AUTH-003"}, root=ROOT)[0]
        bad = self.runner.run_selected(FakeTarget(ui_only_auth=True), ids={"E-AUTH-003"}, root=ROOT)[0]
        self.assertEqual("passed", good["status"])
        self.assertEqual(3, good["attempt_count"])
        self.assertEqual("failed", bad["status"])

    def test_server_denial_has_closed_content_and_metadata_envelope(self):
        mutations = (
            ("response", "unlisted-medical-note"),
            ("logs", "unlisted-medical-note"),
            ("trace", "unlisted-medical-note"),
            ("audit", [{"action": "access.denied", "data_included": False,
                        "medical_note": "unlisted-medical-note"}]),
            ("security_signal", {"kind": "none", "contains_business_content": False,
                                 "student_name": "SENSITIVE_D2_NAME_CANARY"}),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                class DenialLeaker(FakeTarget):
                    def request(self, **kwargs):
                        observed = super().request(**kwargs)
                        observed[field] = value
                        return observed
                case = self.runner.run_selected(DenialLeaker(), ids={"E-AUTH-003"}, root=ROOT)[0]
                self.assertEqual("failed", case["status"])

    def test_model_projection_waits_for_durable_audit_before_provider(self):
        good = self.runner.run_selected(FakeTarget(), ids={"E-AUD-002"}, root=ROOT)[0]
        bad = self.runner.run_selected(
            FakeTarget(provider_before_audit=True), ids={"E-AUD-002"}, root=ROOT
        )[0]
        self.assertEqual("passed", good["status"])
        self.assertEqual(20, good["attempt_count"])
        self.assertEqual("failed", bad["status"])

    def test_model_audit_covers_each_registered_query_capability(self):
        class HiddenAttention(FakeTarget):
            def catalogs(self):
                catalog = super().catalogs()
                catalog["tool"].append({**catalog["tool"][0], "capability_id": "task.today"})
                return catalog

            def request(self, **kwargs):
                observed = super().request(**kwargs)
                if kwargs["surface"] == "model-projection" and kwargs["operation"].startswith("task.today::"):
                    observed["provider_calls"] = 1
                return observed

        case = self.runner.run_selected(HiddenAttention(), ids={"E-AUD-002"}, root=ROOT)[0]
        self.assertEqual("failed", case["status"])

        class RuntimeOnlyCapability(FakeTarget):
            def runtime_model_capabilities(self):
                return super().runtime_model_capabilities() + ["task.today"]

        omitted = self.runner.run_selected(RuntimeOnlyCapability(), ids={"E-AUD-002"}, root=ROOT)[0]
        self.assertEqual("failed", omitted["status"])
        self.assertIn("MODEL_CAPABILITY_CLOSURE_MISMATCH", omitted["failure_codes"])

        class CatalogOmission(FakeTarget):
            def catalogs(self):
                catalog = super().catalogs()
                catalog["mcp"] = []
                return catalog

        hidden = self.runner.run_selected(CatalogOmission(), ids={"E-AUD-002"}, root=ROOT)[0]
        self.assertEqual("failed", hidden["status"])
        self.assertIn("MODEL_CAPABILITY_CLOSURE_MISMATCH", hidden["failure_codes"])

    def test_export_audit_failure_prevents_artifact_and_release(self):
        good = self.runner.run_selected(FakeTarget(), ids={"E-AUD-003"}, root=ROOT)[0]
        self.assertEqual("passed", good["status"])
        self.assertEqual(12, good["attempt_count"])
        for target in (FakeTarget(export_artifact_on_fault=True),
                       FakeTarget(export_release_on_fault=True)):
            self.assertEqual("failed", self.runner.run_selected(
                target, ids={"E-AUD-003"}, root=ROOT
            )[0]["status"])

    def test_audit_query_requires_scope_and_secondary_durable_receipt(self):
        good = self.runner.run_selected(FakeTarget(), ids={"E-AUD-004"}, root=ROOT)[0]
        self.assertEqual("passed", good["status"])
        self.assertEqual(28, good["attempt_count"])
        for target in (FakeTarget(audit_query_bypass=True), FakeTarget(omit_query_receipt=True),
                       FakeTarget(audit_query_fault_leak=True)):
            self.assertEqual("failed", self.runner.run_selected(
                target, ids={"E-AUD-004"}, root=ROOT
            )[0]["status"])

        class MixedDenial(FakeTarget):
            def audit_query_attempt(self, **kwargs):
                observed = super().audit_query_attempt(**kwargs)
                if not kwargs["fixture"]["data"]["audit_query_grants"]:
                    observed["response"] = '{"error":"NOT_FOUND_SAFE"}'
                return observed

        self.assertEqual("failed", self.runner.run_selected(
            MixedDenial(), ids={"E-AUD-004"}, root=ROOT
        )[0]["status"])

    def test_export_route_closure_bcg_and_cleanup_mutations(self):
        class HiddenExport(FakeTarget):
            def runtime_export_entrypoints(self):
                return super().runtime_export_entrypoints() + ["export-cli"]

        class DirectRepositoryWrite(FakeTarget):
            def export_attempt(self, **kwargs):
                observed = super().export_attempt(**kwargs)
                if not kwargs["audit_fault"] and kwargs["surface"] == "export-worker":
                    observed["direct_repository_writes"] = 1
                return observed

        class ResidualObject(FakeTarget):
            def export_cleanup_state(self):
                return {"available_objects": 1, "active_links": 0,
                        "canary_present": True, "residual_sha256": "bad"}

        class NormalWorkerBypass(FakeTarget):
            def export_attempt(self, **kwargs):
                observed = super().export_attempt(**kwargs)
                if not kwargs["audit_fault"] and kwargs["surface"] == "export-worker":
                    observed["bcg_commands"] = 0
                return observed

        class PositiveSignalLeak(FakeTarget):
            def export_attempt(self, **kwargs):
                observed = super().export_attempt(**kwargs)
                if not kwargs["audit_fault"]:
                    observed["security_signal"]["student_name"] = "SENSITIVE_D2_NAME_CANARY"
                return observed

        for target in (HiddenExport(), DirectRepositoryWrite(), ResidualObject(),
                       NormalWorkerBypass(), PositiveSignalLeak()):
            self.assertEqual("failed", self.runner.run_selected(
                target, ids={"E-AUD-003"}, root=ROOT
            )[0]["status"])

    def test_audit_query_route_closure_and_observed_receipt_order(self):
        class HiddenAuditRoute(FakeTarget):
            def runtime_audit_query_entrypoints(self):
                return super().runtime_audit_query_entrypoints() + ["internal-query"]

        class FalseDurability(FakeTarget):
            def observe_audit_query(self, **kwargs):
                observed = super().observe_audit_query(**kwargs)
                if observed["persisted_receipts"] == 1:
                    observed["persisted_receipts"] = 0
                return observed

        class ResponseFirst(FakeTarget):
            def observe_audit_query(self, **kwargs):
                observed = super().observe_audit_query(**kwargs)
                if observed["persisted_receipts"] == 1:
                    observed["response_release_sequence"] = 0
                return observed

        class ReusedReceipt(FakeTarget):
            def audit_query_attempt(self, **kwargs):
                observed = super().audit_query_attempt(**kwargs)
                if observed["audit_receipts"]:
                    observed["audit_receipts"][0]["request_id"] = "old-request"
                return observed

        class RevokedBypass(FakeTarget):
            def audit_query_attempt(self, **kwargs):
                observed = super().audit_query_attempt(**kwargs)
                if kwargs["fixture"]["data"]["audit_query_grants"] and \
                        kwargs["fixture"]["data"]["audit_query_grants"][0]["revoked"]:
                    observed.update(status=200, error_code=None, response='{"count":1}')
                return observed

        for target in (HiddenAuditRoute(), FalseDurability(), ResponseFirst(),
                       ReusedReceipt(), RevokedBypass()):
            self.assertEqual("failed", self.runner.run_selected(
                target, ids={"E-AUD-004"}, root=ROOT
            )[0]["status"])

    def test_export_payload_store_and_fault_metadata_mutations(self):
        class WrongPayloadDigest(FakeTarget):
            def observe_export(self, **kwargs):
                observed = super().observe_export(**kwargs)
                if kwargs["fault_stage"] == "none":
                    observed["object_sha256"] = "0" * 64
                return observed

        class CanaryOnFault(FakeTarget):
            def observe_export(self, **kwargs):
                observed = super().observe_export(**kwargs)
                if kwargs["fault_stage"] == "publish":
                    observed["canary_present"] = True
                return observed

        class MissingDurableReceipt(FakeTarget):
            def observe_export(self, **kwargs):
                observed = super().observe_export(**kwargs)
                if kwargs["fault_stage"] == "none":
                    observed["audit_receipt"] = None
                return observed

        class ResponseBeforeAudit(FakeTarget):
            def observe_export(self, **kwargs):
                observed = super().observe_export(**kwargs)
                if kwargs["fault_stage"] == "none":
                    observed["download_release_sequence"] = 0
                return observed

        class SensitiveFailedJob(FakeTarget):
            def observe_export(self, **kwargs):
                observed = super().observe_export(**kwargs)
                if kwargs["fault_stage"] == "release":
                    observed["metadata_contains_business_content"] = True
                return observed

        class SensitiveCleanupResidual(FakeTarget):
            def export_cleanup_state(self):
                return {"available_objects": 0, "active_links": 0,
                        "canary_present": True, "residual_sha256": "0" * 64}

        for target in (WrongPayloadDigest(), CanaryOnFault(), MissingDurableReceipt(),
                       ResponseBeforeAudit(), SensitiveFailedJob(), SensitiveCleanupResidual()):
            self.assertEqual("failed", self.runner.run_selected(
                target, ids={"E-AUD-003"}, root=ROOT
            )[0]["status"])

    def test_audit_query_owner_only_lifecycle_and_cleanup_mutations(self):
        class OwnerOnlyNoGrantCheck(FakeTarget):
            def audit_query_attempt(self, **kwargs):
                observed = super().audit_query_attempt(**kwargs)
                context = kwargs["request_context"]
                owner = kwargs["fixture"]["data"]["workspaces"][0]
                allowed = (context["actor_id"] == owner["owner_id"] and
                           context["target_workspace_id"] == owner["workspace_id"])
                if not context["audit_fault"]:
                    observed.update(status=200 if allowed else 403,
                                    error_code=None if allowed else "FORBIDDEN",
                                    response='{"count":1}' if allowed else "")
                return observed

        class SessionLifecycleBypass(FakeTarget):
            def audit_query_attempt(self, **kwargs):
                observed = super().audit_query_attempt(**kwargs)
                session = kwargs["fixture"]["data"]["audit_query_sessions"][0]
                if session["revoked"] or session["expires_at"] < kwargs["fixture"]["meta"]["clock"]:
                    observed.update(status=200, error_code=None, response='{"count":1}')
                return observed

        class NoCleanup(FakeTarget):
            def cleanup(self):
                pass

        class CachedResultResidual(FakeTarget):
            def audit_query_cleanup_state(self):
                observed = super().audit_query_cleanup_state()
                observed["cached_results"] = 1
                return observed

        for target in (OwnerOnlyNoGrantCheck(), SessionLifecycleBypass(), NoCleanup(),
                       CachedResultResidual()):
            self.assertEqual("failed", self.runner.run_selected(
                target, ids={"E-AUD-004"}, root=ROOT
            )[0]["status"])

    def test_audit_query_authorization_tuple_omission_mutations(self):
        import copy

        class IgnoreOneBinding(FakeTarget):
            def __init__(self, binding):
                super().__init__()
                self.binding = binding

            def _audit_query_authorized(self, fixture, context):
                case = copy.deepcopy(fixture)
                query = copy.deepcopy(context)
                grants = case["data"]["audit_query_grants"]
                sessions = case["data"]["audit_query_sessions"]
                if self.binding == "grant-action" and grants:
                    grants[0]["action"] = query["action"]
                elif self.binding == "grant-id" and grants:
                    grants[0]["grant_id"] = query["grant_id"]
                elif self.binding == "session-subject" and sessions:
                    sessions[0]["actor_id"] = query["actor_id"]
                elif self.binding == "grant-subject" and grants:
                    grants[0]["actor_id"] = query["actor_id"]
                elif self.binding == "session-id" and sessions:
                    sessions[0]["session_id"] = query["session_id"]
                return super()._audit_query_authorized(case, query)

        for binding in ("grant-action", "grant-id", "session-subject",
                        "grant-subject", "session-id"):
            with self.subTest(binding=binding):
                result = self.runner.run_selected(
                    IgnoreOneBinding(binding), ids={"E-AUD-004"}, root=ROOT
                )[0]
                self.assertEqual("failed", result["status"])

    def test_missing_production_target_is_red_not_skipped_or_green(self):
        report = self.runner.run_cli(root=ROOT)
        self.assertFalse(report["implemented_green"])
        self.assertEqual("target-unavailable", report["status"])
        self.assertEqual(14, len(report["eval_ids"]))
        self.assertTrue({"E-AUTH-001", "E-AUTH-003", "E-AUD-001", "E-AUD-002",
                         "E-AUD-003", "E-AUD-004",
                         "E-AGT-015", "E-AGT-018", "E-AGT-020"}
                        .issubset(set(report["eval_ids"])))

    def test_fixture_provenance_is_checked(self):
        fixture = json.loads((ROOT / "evals/class-os-v1/fixtures/r1/workspace-isolation.synthetic.json")
                             .read_text(encoding="utf-8"))
        fixture["meta"]["synthetic"] = False
        with self.assertRaises(ValueError):
            self.runner.validate_fixture(fixture, "workspace-isolation")

    def test_approval_catalog_and_binding_oracles_kill_bypass(self):
        ids = {"E-AGT-015", "E-AGT-018", "E-AGT-020"}
        good = self.runner.run_selected(FakeTarget(), ids=ids, root=ROOT)
        self.assertTrue(all(case["status"] == "passed" for case in good))
        exposed = self.runner.run_selected(FakeTarget(approval_tool=True), ids={"E-AGT-015"}, root=ROOT)
        replay = self.runner.run_selected(FakeTarget(replay_consumes=True), ids={"E-AGT-020"}, root=ROOT)
        self.assertEqual("failed", exposed[0]["status"])
        disguised = self.runner.run_selected(FakeTarget(disguised_approval=True), ids={"E-AGT-015"}, root=ROOT)
        self.assertEqual("failed", disguised[0]["status"])
        lying_metadata = self.runner.run_selected(
            FakeTarget(disguised_metadata_lies=True), ids={"E-AGT-015"}, root=ROOT
        )
        self.assertEqual("failed", lying_metadata[0]["status"])
        for target in (
            FakeTarget(disguised_metadata_lies=True, receipt_minted=True),
            FakeTarget(disguised_metadata_lies=True, approval_state_changed=True),
            FakeTarget(disguised_metadata_lies=True, hidden_business_write=True),
        ):
            self.assertEqual(
                "failed", self.runner.run_selected(target, ids={"E-AGT-015"}, root=ROOT)[0]["status"]
            )
        self.assertEqual("failed", replay[0]["status"])
        malformed = self.runner.run_selected(FakeTarget(malformed_approval=True), ids={"E-AGT-020"}, root=ROOT)
        self.assertEqual("failed", malformed[0]["status"])
        denied_replay = self.runner.run_selected(
            FakeTarget(rejected_replay_consumes=True), ids={"E-AGT-020"}, root=ROOT
        )
        self.assertEqual("failed", denied_replay[0]["status"])

    def test_versioned_risk_matrix_and_monotonicity_kill_downgrade(self):
        ids = {f"E-RISK-{index:03d}" for index in range(1, 6)}
        good = self.runner.run_selected(FakeTarget(), ids=ids, root=ROOT)
        bad = self.runner.run_selected(FakeTarget(risk_downgrade=True), ids=ids, root=ROOT)
        self.assertEqual(ids, {case["eval_id"] for case in good})
        self.assertTrue(all(case["status"] == "passed" for case in good))
        self.assertTrue(any(case["status"] == "failed" for case in bad))
        combo = self.runner.run_selected(FakeTarget(risk_combo_downgrade=True), ids=ids, root=ROOT)
        self.assertTrue(any(case["status"] == "failed" for case in combo))
        ignored_version = self.runner.run_selected(FakeTarget(ignores_policy_version=True), ids=ids, root=ROOT)
        self.assertTrue(all(case["status"] == "failed" for case in ignored_version))
        delete_downgrade = self.runner.run_selected(FakeTarget(delete_downgrade=True), ids=ids, root=ROOT)
        self.assertTrue(any(case["status"] == "failed" for case in delete_downgrade))

    def test_risk_policy_definition_drift_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="class-os-risk-oracle-") as temporary:
            root = Path(temporary)
            path = root / self.runner.POLICY_RELATIVE_PATH
            path.parent.mkdir(parents=True)
            source = (ROOT / self.runner.POLICY_RELATIVE_PATH).read_bytes().replace(b"\r\n", b"\n")
            for representation in (source, source.replace(b"\n", b"\r\n")):
                path.write_bytes(representation)
                self.runner._validate_risk_policy(root)
            path.write_bytes(source.replace(b"\n", b"\r\r\n"))
            with self.assertRaises(ValueError):
                self.runner._validate_risk_policy(root)
            path.write_bytes(source.replace(b"r1.0", b"r0.9"))
            with self.assertRaises(ValueError):
                self.runner._validate_risk_policy(root)


if __name__ == "__main__":
    unittest.main()
