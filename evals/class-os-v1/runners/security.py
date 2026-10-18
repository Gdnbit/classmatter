"""T-REVAL-003 security oracle slice; never self-certifies product implementation.

The test-double contract characterises oracles. A production driver must be bound
to actual API/Query Gateway, durable audit and provider-call observation before
these cases can produce implemented-green evidence. No such driver exists yet.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from itertools import product
from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "evals/class-os-v1/fixtures/r1"
WORKSPACE_SURFACES = ("ui-api", "rest", "query-tool", "export-preview")
AUDIT_SURFACES = ("ui-api", "rest", "query-tool")
SUPPORTED = frozenset({
    "E-AUTH-001", "E-AUTH-003", "E-AUD-001", "E-AUD-002", "E-AUD-003", "E-AUD-004",
    "E-AGT-015", "E-AGT-018", "E-AGT-020",
    "E-RISK-001", "E-RISK-002", "E-RISK-003", "E-RISK-004", "E-RISK-005",
})
APPROVAL_TOOL_ALIASES = ("approval.approve", "approve", "proposal.approve", "approval_confirm")
CAPABILITY_FIELDS = {
    "capability_id", "operation_family", "side_effect", "risk_floor",
    "proposal_effect", "approval_effect", "receipt_effect", "schema_sha256",
}
RISK_RANK = {"W1": 1, "W2": 2, "X": 3}
POLICY_RELATIVE_PATH = Path("evals/class-os-v1/runners/risk-policy-r1.synthetic.json")
POLICY_SHA256 = "1b7aec7579f20fd79e5b54a1e4cacab7ef5200e0cae7577db297328a3bd892ef"


class SecurityTarget(Protocol):
    """Test adapter port; implementation must observe response and side effects."""

    def prepare(self, fixture: dict[str, Any]) -> None: ...

    def request(
        self, *, surface: str, operation: str, actor_id: str,
        workspace_id: str, resource_id: str, audit_fault: bool = False,
    ) -> dict[str, Any]: ...

    def cleanup(self) -> None: ...

    def catalogs(self) -> dict[str, list[str]]: ...

    def runtime_model_capabilities(self) -> list[str]: ...

    def export_attempt(
        self, *, surface: str, fault_stage: str, fixture: dict[str, Any],
        audit_fault: bool = True,
    ) -> dict[str, Any]: ...

    def export_entrypoints(self) -> list[str]: ...

    def runtime_export_entrypoints(self) -> list[str]: ...

    def export_cleanup_state(self) -> dict[str, Any]: ...

    def observe_export(
        self, *, surface: str, fault_stage: str, export_id: str, request_id: str,
    ) -> dict[str, Any]: ...

    def audit_query_attempt(
        self, *, surface: str, fixture: dict[str, Any], request_context: dict[str, Any],
    ) -> dict[str, Any]: ...

    def audit_query_entrypoints(self) -> list[str]: ...

    def runtime_audit_query_entrypoints(self) -> list[str]: ...

    def observe_audit_query(
        self, *, surface: str, request_context: dict[str, Any],
    ) -> dict[str, Any]: ...

    def audit_query_cleanup_state(self) -> dict[str, Any]: ...

    def agent_tool_attempt(self, name: str) -> dict[str, Any]: ...

    def approval_attempt(self, variant: str, fixture: dict[str, Any]) -> dict[str, Any]: ...

    def evaluate_risk(self, command: dict[str, Any]) -> dict[str, Any]: ...


def validate_fixture(value: Any, purpose: str) -> None:
    if not isinstance(value, dict) or set(value) != {"meta", "data"}:
        raise ValueError("security fixture shape is invalid")
    meta = value["meta"]
    if (
        not isinstance(meta, dict)
        or meta.get("schema") != "class-os.synthetic-fixture/v1"
        or meta.get("purpose") != purpose
        or meta.get("synthetic") is not True
        or meta.get("contains_real_person_data") is not False
        or meta.get("provenance") != "deterministic-fixture-factory"
        or not isinstance(value["data"], dict)
    ):
        raise ValueError("security fixture provenance is invalid")


def load_fixture(root: Path, filename: str, purpose: str) -> dict[str, Any]:
    value = json.loads((root / "evals/class-os-v1/fixtures/r1" / filename).read_text(encoding="utf-8"))
    validate_fixture(value, purpose)
    return value


def _attempt(value: Any) -> dict[str, Any]:
    required = {
        "status", "error_code", "response", "logs", "trace", "audit",
        "provider_calls", "business_writes", "security_signal",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("security target evidence shape is invalid")
    if (
        type(value["status"]) is not int
        or not (value["error_code"] is None or isinstance(value["error_code"], str))
        or any(not isinstance(value[key], str) for key in ("response", "logs", "trace"))
        or not isinstance(value["audit"], list)
        or type(value["provider_calls"]) is not int
        or type(value["business_writes"]) is not int
        or not isinstance(value["security_signal"], dict)
        or set(value["security_signal"]) != {"kind", "contains_business_content"}
        or not isinstance(value["security_signal"]["kind"], str)
        or type(value["security_signal"]["contains_business_content"]) is not bool
    ):
        raise ValueError("security target evidence values are invalid")
    return value


def _case(eval_id: str, observations: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    return {
        "eval_id": eval_id,
        "status": "passed" if not errors else "failed",
        "attempt_count": len(observations),
        "failure_codes": sorted(set(errors)),
        "evidence_kind": "oracle-test-double-only",
        "implemented_green": False,
    }


def _closed_result(value: Any, fields: set[str], bool_fields: tuple[str, ...] = (),
                   int_fields: tuple[str, ...] = ()) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == fields
        and all(type(value[field]) is bool for field in bool_fields)
        and all(type(value[field]) is int and value[field] >= 0 for field in int_fields)
    )


def _workspace_isolation(target: SecurityTarget, root: Path) -> dict[str, Any]:
    fixture = copy.deepcopy(load_fixture(root, "workspace-isolation.synthetic.json", "workspace-isolation"))
    workspaces = fixture["data"]["workspaces"]
    students = fixture["data"]["students"]
    if len(workspaces) != 2 or len(students) != 2:
        raise ValueError("workspace isolation fixture is incomplete")
    actor, foreign = workspaces
    foreign_student = next(row for row in students if row["workspace_id"] == foreign["workspace_id"])
    foreign_student["display_name"] = "WORKSPACE_B_CANARY"
    foreign_class = next(row for row in fixture["data"]["classes"]
                         if row["workspace_id"] == foreign["workspace_id"])
    foreign_class["display_name"] = "WORKSPACE_B_CLASS_CANARY"
    forbidden = tuple({
        foreign_student["display_name"], foreign_student["student_id"],
        foreign_student["term_id"], foreign_student["class_id"],
        foreign["label"], foreign["workspace_id"], foreign["owner_id"],
        foreign_class["display_name"],
    })
    private_names = (foreign_student["display_name"], foreign["label"], foreign_class["display_name"])
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    denial_shape: tuple[int, str] | None = None
    target.prepare(fixture)
    try:
        for surface in WORKSPACE_SURFACES:
            try:
                observed = _attempt(target.request(
                    surface=surface,
                    operation="student.read",
                    actor_id=actor["owner_id"],
                    workspace_id=actor["workspace_id"],
                    resource_id=foreign_student["student_id"],
                ))
            except Exception:
                errors.append(f"{surface}:TARGET_ERROR")
                continue
            observations.append(observed)
            if (observed["status"], observed["error_code"]) not in (
                (403, "FORBIDDEN"), (404, "NOT_FOUND_SAFE")
            ):
                errors.append(f"{surface}:NOT_DENIED")
            current_shape = (observed["status"], observed["error_code"])
            if denial_shape is None:
                denial_shape = current_shape
            elif denial_shape != current_shape:
                errors.append(f"{surface}:INCONSISTENT_DENIAL")
            if any(marker in observed[key] for marker in forbidden for key in ("response", "logs", "trace")):
                errors.append(f"{surface}:FOREIGN_DATA_LEAK")
            if observed["provider_calls"] != 0 or observed["business_writes"] != 0:
                errors.append(f"{surface}:SIDE_EFFECT")
            audit = observed["audit"]
            if (
                len(audit) != 1
                or not isinstance(audit[0], dict)
                or audit[0].get("action") != "access.denied"
                or audit[0].get("data_included", audit[0].get("payload_included")) is not False
                or any(marker in json.dumps(audit, ensure_ascii=False) for marker in private_names)
            ):
                errors.append(f"{surface}:DENIAL_AUDIT_MISSING_OR_VERBOSE")
    finally:
        target.cleanup()
    if len(observations) != len(WORKSPACE_SURFACES):
        errors.append("INCOMPLETE_SURFACE_COVERAGE")
    return _case("E-AUTH-001", observations, errors)


def _server_side_authorization(target: SecurityTarget, root: Path) -> dict[str, Any]:
    fixture = copy.deepcopy(load_fixture(root, "workspace-isolation.synthetic.json", "workspace-isolation"))
    workspace = fixture["data"]["workspaces"][0]
    student = next(row for row in fixture["data"]["students"]
                   if row["workspace_id"] == workspace["workspace_id"])
    student["display_name"] = "SENSITIVE_D2_NAME_CANARY"
    actor_id = "synthetic-unprivileged-actor"
    fixture["data"]["denied_actor"] = {
        "actor_id": actor_id, "workspace_id": workspace["workspace_id"],
        "student_id": student["student_id"], "student_read_granted": False,
    }
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    target.prepare(fixture)
    try:
        # These calls bypass the UI completely; hidden controls are not an authorization proof.
        for surface in ("rest", "query-tool", "export-preview"):
            try:
                observed = _attempt(target.request(
                    surface=surface, operation="student.read", actor_id=actor_id,
                    workspace_id=workspace["workspace_id"], resource_id=student["student_id"],
                ))
            except Exception:
                errors.append(f"{surface}:TARGET_ERROR")
                continue
            observations.append(observed)
            if (observed["status"], observed["error_code"]) not in (
                (403, "FORBIDDEN"), (404, "NOT_FOUND_SAFE")
            ):
                errors.append(f"{surface}:UNPRIVILEGED_REQUEST_NOT_DENIED")
            allowed_body = (
                "", '{"error":"FORBIDDEN"}' if observed["status"] == 403
                else '{"error":"NOT_FOUND_SAFE"}',
            )
            if observed["response"] not in allowed_body or observed["logs"] or observed["trace"]:
                errors.append(f"{surface}:DENIAL_CONTENT_NOT_CLOSED")
            if observed["provider_calls"] != 0 or observed["business_writes"] != 0:
                errors.append(f"{surface}:DENIAL_SIDE_EFFECT")
            audit = observed["audit"]
            if (audit != [{"action": "access.denied", "data_included": False}]
                    or observed["security_signal"] != {
                        "kind": "none", "contains_business_content": False
                    }):
                errors.append(f"{surface}:DENIAL_METADATA_NOT_CLOSED")
    finally:
        target.cleanup()
    if len(observations) != 3:
        errors.append("INCOMPLETE_SERVER_AUTH_SURFACES")
    return _case("E-AUTH-003", observations, errors)


def _model_capability_closure(target: SecurityTarget, errors: list[str]) -> list[str]:
    try:
        catalogs = target.catalogs()
        runtime = target.runtime_model_capabilities()
    except Exception:
        errors.append("MODEL_CAPABILITY_REGISTRY_UNAVAILABLE")
        return []
    if (not isinstance(catalogs, dict) or set(catalogs) != {"tool", "skill", "mcp"}
            or not isinstance(runtime, list) or not runtime
            or any(not isinstance(item, str) or not item for item in runtime)
            or len(set(runtime)) != len(runtime)):
        errors.append("MODEL_CAPABILITY_REGISTRY_INVALID")
        return []
    exposed: set[str] = set()
    for descriptors in catalogs.values():
        if not isinstance(descriptors, list):
            errors.append("MODEL_CAPABILITY_CATALOG_INVALID")
            return []
        for descriptor in descriptors:
            if (not isinstance(descriptor, dict) or set(descriptor) != CAPABILITY_FIELDS
                    or descriptor.get("operation_family") not in ("query", "draft")
                    or not isinstance(descriptor.get("capability_id"), str)
                    or not descriptor["capability_id"] or descriptor["capability_id"] in exposed):
                errors.append("MODEL_CAPABILITY_CATALOG_INVALID")
                return []
            exposed.add(descriptor["capability_id"])
    if set(runtime) != exposed or "attention.list" not in exposed:
        errors.append("MODEL_CAPABILITY_CLOSURE_MISMATCH")
    return sorted(set(runtime) | exposed | {"attention.list"})


def _audit_unavailable(target: SecurityTarget, root: Path, *, eval_id: str = "E-AUD-001") -> dict[str, Any]:
    fixture = copy.deepcopy(load_fixture(root, "audit-failure.synthetic.json", "audit-fail-closed"))
    event = next((row for row in fixture["data"].get("audit_events", []) if row.get("fault")), None)
    if event is None:
        raise ValueError("audit failure fixture has no fault point")
    fixture["data"]["sensitive_subjects"] = [
        {"kind": "student.d2-name", "resource_id": event["resource_ref"],
         "canary": "SENSITIVE_D2_NAME_CANARY"},
        {"kind": "student.d2-detail", "resource_id": event["resource_ref"],
         "canary": "SENSITIVE_CANARY"},
        {"kind": "student.d2-timeline", "resource_id": event["resource_ref"],
         "canary": "SENSITIVE_D2_TIMELINE_CANARY"},
        {"kind": "student.d2-event-list", "resource_id": event["resource_ref"],
         "canary": "SENSITIVE_D2_EVENT_CANARY"},
        {"kind": "record.d3-detail", "resource_id": "synthetic-d3-record-audit-fault",
         "canary": "SENSITIVE_D3_CANARY"},
    ]
    forbidden = tuple(row["canary"] for row in fixture["data"]["sensitive_subjects"])
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    target.prepare(copy.deepcopy(fixture))
    try:
        surfaces = AUDIT_SURFACES if eval_id == "E-AUD-001" else ("model-projection",)
        capabilities = _model_capability_closure(target, errors) if eval_id == "E-AUD-002" else []
        for surface in surfaces:
            operations = (
                tuple(row["kind"] for row in fixture["data"]["sensitive_subjects"])
                if eval_id == "E-AUD-001" else
                tuple(f"{capability}::{row['kind']}" for capability in capabilities
                      for row in fixture["data"]["sensitive_subjects"])
            )
            for operation in operations:
                try:
                    observed = _attempt(target.request(
                        surface=surface,
                        operation=operation,
                        actor_id=event["actor_id"],
                        workspace_id=event["workspace_id"],
                        resource_id=next(row["resource_id"] for row in fixture["data"]["sensitive_subjects"]
                                         if row["kind"] == operation.split("::")[-1]),
                        audit_fault=True,
                    ))
                except Exception:
                    errors.append(f"{surface}/{operation}:TARGET_ERROR")
                    continue
                observations.append(observed)
                label = f"{surface}/{operation}"
                if observed["status"] != 503 or observed["error_code"] != "AUDIT_UNAVAILABLE":
                    errors.append(f"{label}:AUDIT_FAILURE_NOT_DENIED")
                if (
                    any(marker in observed[key] for marker in forbidden for key in ("response", "logs", "trace"))
                    or any(marker in json.dumps(observed["audit"], ensure_ascii=False) for marker in forbidden)
                    or observed["response"] not in ("", '{"error":"AUDIT_UNAVAILABLE"}')
                    or observed["logs"] != ""
                    or observed["trace"] != ""
                    or observed["audit"] != []
                    or observed["provider_calls"] != 0
                    or observed["business_writes"] != 0
                ):
                    errors.append(f"{label}:SENSITIVE_RELEASE_OR_SIDE_EFFECT")
                if observed["security_signal"] != {
                    "kind": "audit-unavailable", "contains_business_content": False
                }:
                    errors.append(f"{label}:NO_SECURITY_SIGNAL")
    finally:
        target.cleanup()
    expected_count = len(surfaces) * len(fixture["data"]["sensitive_subjects"])
    if eval_id == "E-AUD-002":
        expected_count *= len(capabilities)
    if len(observations) != expected_count:
        errors.append("INCOMPLETE_AUDIT_FAILURE_COVERAGE")
    return _case(eval_id, observations, errors)


EXPORT_FIELDS = {
    "status", "error_code", "response", "logs", "trace", "audit",
    "artifact_created", "artifact_released", "temp_objects_available",
    "download_bytes", "active_links", "provider_calls", "business_writes",
    "bcg_commands", "direct_repository_writes",
    "artifact_sha256", "download_sha256", "security_signal",
}


def _entrypoint_closure(
    visible: Any, runtime: Any, minimum: set[str], label: str,
    errors: list[str],
) -> list[str]:
    if (not isinstance(visible, list) or not isinstance(runtime, list)
            or any(not isinstance(item, str) or not item for item in visible + runtime)
            or len(set(visible)) != len(visible) or len(set(runtime)) != len(runtime)):
        errors.append(f"{label}:ENTRYPOINT_REGISTRY_INVALID")
        return []
    if set(visible) != set(runtime) or not minimum.issubset(set(runtime)):
        errors.append(f"{label}:ENTRYPOINT_CLOSURE_MISMATCH")
    return sorted(set(visible) | set(runtime) | minimum)


def _export_fixture(root: Path) -> dict[str, Any]:
    fixture = copy.deepcopy(load_fixture(root, "audit-failure.synthetic.json", "audit-fail-closed"))
    scope = load_fixture(root, "workspace-isolation.synthetic.json", "workspace-isolation")
    workspace = scope["data"]["workspaces"][0]["workspace_id"]
    student = next(row for row in scope["data"]["students"] if row["workspace_id"] == workspace)
    payload = {
        "workspace_id": workspace, "student_id": student["student_id"],
        "student_name": "SYNTHETIC_D2_EXPORT_CANARY",
        "record": {"record_id": "synthetic-d3-export-record",
                   "note": "SYNTHETIC_D3_EXPORT_CANARY"},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fixture["data"]["export"] = {
        "export_id": "synthetic-sensitive-export-r1", "payload": payload,
        "payload_sha256": hashlib.sha256(encoded).hexdigest(),
        "payload_byte_count": len(encoded),
        "canaries": ["SYNTHETIC_D2_EXPORT_CANARY", "SYNTHETIC_D3_EXPORT_CANARY"],
    }
    return fixture


def _export_evidence(value: Any) -> bool:
    return (
        _closed_result(value, EXPORT_FIELDS, int_fields=(
            "artifact_created", "artifact_released", "temp_objects_available",
            "download_bytes", "active_links", "provider_calls", "business_writes",
            "bcg_commands", "direct_repository_writes",
        ))
        and type(value["status"]) is int
        and (value["error_code"] is None or isinstance(value["error_code"], str))
        and all(isinstance(value[key], str) for key in ("response", "logs", "trace"))
        and isinstance(value["audit"], list)
        and all(value[field] is None or isinstance(value[field], str)
                for field in ("artifact_sha256", "download_sha256"))
        and isinstance(value["security_signal"], dict)
    )


def _export_audit_failure(target: SecurityTarget, root: Path) -> dict[str, Any]:
    fixture = _export_fixture(root)
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        surfaces = _entrypoint_closure(
            target.export_entrypoints(), target.runtime_export_entrypoints(),
            {"export-api", "export-worker", "export-download"}, "export", errors,
        )
    except Exception:
        surfaces = []
        errors.append("export:ENTRYPOINT_REGISTRY_UNAVAILABLE")
    for surface in surfaces:
        for fault_stage in ("none", "register", "publish", "release"):
            audit_fault = fault_stage != "none"
            case_fixture = copy.deepcopy(fixture)
            export_id = case_fixture["data"]["export"]["export_id"]
            request_id = hashlib.sha256(f"{surface}:{fault_stage}:{export_id}".encode("utf-8")).hexdigest()[:32]
            case_fixture["data"]["export"]["request_id"] = request_id
            target.prepare(copy.deepcopy(case_fixture))
            try:
                try:
                    observed = target.export_attempt(
                        surface=surface, fault_stage=fault_stage,
                        fixture=copy.deepcopy(case_fixture), audit_fault=audit_fault,
                    )
                    durable = target.observe_export(
                        surface=surface, fault_stage=fault_stage,
                        export_id=export_id, request_id=request_id,
                    )
                except Exception:
                    errors.append(f"{surface}/{fault_stage}:TARGET_ERROR")
                    continue
                observations.append(observed)
                label = f"{surface}/{fault_stage}"
                if not _export_evidence(observed):
                    errors.append(f"{label}:EVIDENCE_INVALID")
                    continue
                if (not _closed_result(durable, {
                        "request_id", "export_id", "audit_receipt", "bcg_receipt_count",
                        "audit_commit_sequence", "artifact_publish_sequence",
                        "link_activation_sequence", "download_release_sequence",
                        "object_count", "index_count", "egress_bytes", "object_sha256",
                        "egress_sha256", "canary_present", "failed_job_metadata_count",
                        "metadata_contains_business_content",
                    }, int_fields=(
                        "bcg_receipt_count", "audit_commit_sequence", "artifact_publish_sequence",
                        "link_activation_sequence", "download_release_sequence", "object_count",
                        "index_count", "egress_bytes", "failed_job_metadata_count",
                    )) or durable["request_id"] != request_id or durable["export_id"] != export_id
                        or type(durable["canary_present"]) is not bool
                        or type(durable["metadata_contains_business_content"]) is not bool):
                    errors.append(f"{label}:EXPORT_OBSERVER_INVALID")
                    continue
                expected_writes = 0 if surface == "export-download" else 1
                if not audit_fault:
                    expected_receipt = {
                        "action": "export.release", "request_id": request_id,
                        "export_id": export_id,
                        "payload_sha256": case_fixture["data"]["export"]["payload_sha256"],
                        "payload_included": False,
                    }
                    if (observed["status"], observed["error_code"], observed["response"]) != (
                        200, None, '{"export":"ready"}'
                    ) or observed["audit"] != [{
                        "action": "export.release", "durable": True,
                        "before_release": True, "payload_included": False,
                    }] or observed["artifact_created"] != 1 or observed["artifact_released"] != 1 \
                            or observed["download_bytes"] != case_fixture["data"]["export"]["payload_byte_count"] \
                            or observed["artifact_sha256"] != case_fixture["data"]["export"]["payload_sha256"] \
                            or observed["download_sha256"] != case_fixture["data"]["export"]["payload_sha256"] \
                            or observed["active_links"] != 1 \
                            or observed["temp_objects_available"] != 0 \
                            or observed["business_writes"] != expected_writes \
                            or observed["bcg_commands"] != expected_writes:
                        errors.append(f"{label}:EXPORT_POSITIVE_CONTROL_INVALID")
                    if (durable["audit_receipt"] != expected_receipt
                            or durable["bcg_receipt_count"] != expected_writes
                            or durable["object_count"] != 1 or durable["index_count"] != 1
                            or durable["egress_bytes"] != case_fixture["data"]["export"]["payload_byte_count"]
                            or durable["object_sha256"] != case_fixture["data"]["export"]["payload_sha256"]
                            or durable["egress_sha256"] != case_fixture["data"]["export"]["payload_sha256"]
                            or not durable["canary_present"] or durable["failed_job_metadata_count"] != 0
                            or durable["metadata_contains_business_content"]
                            or not (0 < durable["audit_commit_sequence"]
                                    < durable["artifact_publish_sequence"]
                                    < durable["link_activation_sequence"]
                                    < durable["download_release_sequence"])):
                        errors.append(f"{label}:EXPORT_NOT_DURABLY_ORDERED_OR_BOUND")
                else:
                    if (observed["status"], observed["error_code"]) != (503, "AUDIT_UNAVAILABLE"):
                        errors.append(f"{label}:AUDIT_FAILURE_NOT_DENIED")
                    if (observed["response"] not in ("", '{"error":"AUDIT_UNAVAILABLE"}')
                            or observed["audit"] != []
                            or any(observed[field] != 0 for field in (
                                "artifact_created", "artifact_released", "temp_objects_available",
                                "download_bytes", "active_links",
                            ))):
                        errors.append(f"{label}:EXPORT_CREATED_OR_RELEASED")
                    metadata_writes = 0 if fault_stage == "register" or surface == "export-download" else 1
                    if (observed["business_writes"] != metadata_writes
                            or observed["bcg_commands"] != metadata_writes
                            or observed["artifact_sha256"] is not None
                            or observed["download_sha256"] is not None
                            or durable["audit_receipt"] is not None
                            or durable["bcg_receipt_count"] != metadata_writes
                            or durable["failed_job_metadata_count"] != metadata_writes
                            or durable["metadata_contains_business_content"]
                            or any(durable[field] != 0 for field in (
                                "audit_commit_sequence", "artifact_publish_sequence",
                                "link_activation_sequence", "download_release_sequence",
                                "object_count", "index_count", "egress_bytes",
                            )) or durable["object_sha256"] is not None
                            or durable["egress_sha256"] is not None
                            or durable["canary_present"]):
                        errors.append(f"{label}:EXPORT_FAULT_SIDE_EFFECT_OR_LEAK")
                if (observed["logs"] or observed["trace"] or observed["provider_calls"] != 0
                        or observed["direct_repository_writes"] != 0):
                    errors.append(f"{label}:BYPASS_OR_LEAK")
                expected_signal = {
                    "kind": "audit-unavailable" if audit_fault else "none",
                    "contains_business_content": False,
                }
                if observed["security_signal"] != expected_signal:
                    errors.append(f"{label}:SECURITY_SIGNAL_INVALID")
            finally:
                target.cleanup()
                try:
                    cleanup = target.export_cleanup_state()
                    if cleanup != {"available_objects": 0, "active_links": 0,
                                   "canary_present": False, "residual_sha256": None}:
                        errors.append(f"{surface}/{fault_stage}:CLEANUP_RESIDUAL")
                except Exception:
                    errors.append(f"{surface}/{fault_stage}:CLEANUP_OBSERVATION_ERROR")
    if len(observations) != len(surfaces) * 4:
        errors.append("INCOMPLETE_EXPORT_AUDIT_COVERAGE")
    return _case("E-AUD-003", observations, errors)


AUDIT_QUERY_FIELDS = {
    "status", "error_code", "response", "logs", "trace", "provider_calls",
    "business_writes", "audit_receipts", "security_signal",
}


def _audit_query_fixture(root: Path) -> dict[str, Any]:
    fixture = copy.deepcopy(load_fixture(root, "audit-failure.synthetic.json", "audit-fail-closed"))
    scope = load_fixture(root, "workspace-isolation.synthetic.json", "workspace-isolation")
    workspaces = scope["data"]["workspaces"]
    if len(workspaces) != 2:
        raise ValueError("audit-query fixture requires two workspaces")
    owner = workspaces[0]["owner_id"]
    fixture["data"]["workspaces"] = copy.deepcopy(workspaces)
    fixture["data"]["audit_events"].append({
        "action": "record.create.synthetic", "actor_id": workspaces[1]["owner_id"],
        "audit_event_id": "synthetic-workspace-b-audit-event",
        "correlation_id": "synthetic-workspace-b-correlation",
        "occurred_at": fixture["meta"]["clock"], "payload_included": False,
        "resource_ref": "synthetic-workspace-b-resource",
        "workspace_id": workspaces[1]["workspace_id"],
    })
    fixture["data"]["audit_query_grants"] = [
        {"grant_id": "grant-active", "actor_id": owner,
         "workspace_id": workspaces[0]["workspace_id"], "action": "audit.read",
         "expires_at": "2026-09-02T08:00:00+08:00", "revoked": False},
    ]
    fixture["data"]["audit_query_sessions"] = [
        {"session_id": f"session-{owner}", "actor_id": owner,
         "expires_at": "2026-09-02T08:00:00+08:00", "revoked": False}
    ]
    return fixture


def _audit_query(target: SecurityTarget, root: Path) -> dict[str, Any]:
    fixture = _audit_query_fixture(root)
    workspaces = fixture["data"]["workspaces"]
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        surfaces = _entrypoint_closure(
            target.audit_query_entrypoints(), target.runtime_audit_query_entrypoints(),
            {"ui-api", "rest"}, "audit-query", errors,
        )
    except Exception:
        surfaces = []
        errors.append("audit-query:ENTRYPOINT_REGISTRY_UNAVAILABLE")
    variants = ("no-grant", "cross-workspace", "grant-expired", "grant-revoked",
                "session-expired", "session-revoked", "wrong-action-grant",
                "wrong-grant-id", "session-subject-mismatch", "grant-subject-mismatch",
                "unknown-session-id", "authorized", "non-owner-authorized", "audit-fault")
    for surface in surfaces:
        for index, variant in enumerate(variants):
            case_fixture = copy.deepcopy(fixture)
            actor_id = ("synthetic-valid-grantee" if variant == "non-owner-authorized"
                        else workspaces[0]["owner_id"])
            if variant == "no-grant":
                case_fixture["data"]["audit_query_grants"] = []
            elif variant == "grant-expired":
                case_fixture["data"]["audit_query_grants"][0]["expires_at"] = "2026-08-31T08:00:00+08:00"
            elif variant == "grant-revoked":
                case_fixture["data"]["audit_query_grants"][0]["revoked"] = True
            elif variant == "session-expired":
                case_fixture["data"]["audit_query_sessions"][0]["expires_at"] = "2026-08-31T08:00:00+08:00"
            elif variant == "session-revoked":
                case_fixture["data"]["audit_query_sessions"][0]["revoked"] = True
            elif variant == "wrong-action-grant":
                case_fixture["data"]["audit_query_grants"][0]["action"] = "student.read"
            elif variant == "wrong-grant-id":
                case_fixture["data"]["audit_query_grants"][0]["grant_id"] = "grant-other-valid"
            elif variant == "session-subject-mismatch":
                case_fixture["data"]["audit_query_sessions"][0]["actor_id"] = "synthetic-other-actor"
            elif variant == "grant-subject-mismatch":
                case_fixture["data"]["audit_query_grants"][0]["actor_id"] = "synthetic-other-actor"
            elif variant == "non-owner-authorized":
                case_fixture["data"]["audit_query_grants"][0]["actor_id"] = actor_id
                case_fixture["data"]["audit_query_sessions"][0].update(
                    actor_id=actor_id, session_id=f"session-{actor_id}")
            target_workspace = (workspaces[1]["workspace_id"] if variant == "cross-workspace"
                                else workspaces[0]["workspace_id"])
            grant_id = "grant-active"
            query_scope = {
                "actor_id": actor_id,
                "session_id": ("session-unknown" if variant == "unknown-session-id"
                               else f"session-{actor_id}"),
                "target_workspace_id": target_workspace, "grant_id": grant_id,
                "surface": surface, "action": "audit.read", "filter": "synthetic-audit-event-only",
            }
            query_hash = hashlib.sha256(json.dumps(
                query_scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            request_id = hashlib.sha256(f"{query_hash}:{index}".encode("ascii")).hexdigest()[:32]
            context = {**query_scope, "request_id": request_id, "query_scope_hash": query_hash,
                       "occurred_at": case_fixture["meta"]["clock"], "result_count": 1,
                       "audit_fault": variant == "audit-fault"}
            expected_receipt = {
                "action": "audit.query", "actor_id": actor_id,
                "workspace_id": target_workspace, "request_id": request_id,
                "query_scope_hash": query_hash, "occurred_at": case_fixture["meta"]["clock"],
                "result_count": 1, "payload_included": False,
            }
            target.prepare(copy.deepcopy(case_fixture))
            try:
                try:
                    observed = target.audit_query_attempt(
                        surface=surface, fixture=copy.deepcopy(case_fixture),
                        request_context=copy.deepcopy(context),
                    )
                    durable = target.observe_audit_query(
                        surface=surface, request_context=copy.deepcopy(context),
                    )
                except Exception:
                    errors.append(f"{surface}/{variant}:TARGET_ERROR")
                    continue
                observations.append(observed)
                label = f"{surface}/{variant}"
                if (not _closed_result(observed, AUDIT_QUERY_FIELDS,
                                       int_fields=("provider_calls", "business_writes"))
                        or type(observed["status"]) is not int
                        or not (observed["error_code"] is None or isinstance(observed["error_code"], str))
                        or any(not isinstance(observed[key], str) for key in ("response", "logs", "trace"))
                        or not isinstance(observed["audit_receipts"], list)
                        or not isinstance(observed["security_signal"], dict)
                        or not _closed_result(durable, {
                            "persisted_receipts", "receipt", "audit_commit_sequence",
                            "response_release_sequence",
                        }, int_fields=(
                            "persisted_receipts", "audit_commit_sequence", "response_release_sequence",
                        ))):
                    errors.append(f"{label}:EVIDENCE_INVALID")
                    continue
                if (observed["logs"] or observed["trace"]
                        or observed["provider_calls"] != 0 or observed["business_writes"] != 0):
                    errors.append(f"{label}:QUERY_SIDE_EFFECT_OR_LEAK")
                if variant in ("authorized", "non-owner-authorized"):
                    if ((observed["status"], observed["error_code"], observed["response"]) != (
                            200, None, '{"count":1}'
                        ) or observed["audit_receipts"] != [expected_receipt]
                            or durable["persisted_receipts"] != 1
                            or durable["receipt"] != expected_receipt
                            or durable["audit_commit_sequence"] < 1
                            or durable["response_release_sequence"] <= durable["audit_commit_sequence"]):
                        errors.append(f"{label}:AUTHORIZED_QUERY_NOT_DURABLY_AUDITED")
                elif variant == "audit-fault":
                    if ((observed["status"], observed["error_code"]) != (503, "AUDIT_UNAVAILABLE")
                            or observed["response"] not in ("", '{"error":"AUDIT_UNAVAILABLE"}')
                            or observed["audit_receipts"] != []):
                        errors.append(f"{label}:AUDIT_QUERY_FAULT_NOT_CLOSED")
                else:
                    denial = (observed["status"], observed["error_code"])
                    allowed_body = (
                        "", '{"error":"FORBIDDEN"}' if denial == (403, "FORBIDDEN")
                        else '{"error":"NOT_FOUND_SAFE"}',
                    )
                    if (denial not in ((403, "FORBIDDEN"), (404, "NOT_FOUND_SAFE"))
                            or observed["response"] not in allowed_body
                            or observed["audit_receipts"] != []):
                        errors.append(f"{label}:AUDIT_QUERY_NOT_DENIED")
                if variant not in ("authorized", "non-owner-authorized") and durable != {
                    "persisted_receipts": 0, "receipt": None,
                    "audit_commit_sequence": 0, "response_release_sequence": 1,
                }:
                    errors.append(f"{label}:UNEXPECTED_AUDIT_STORE_STATE")
                expected_signal = {
                    "kind": "audit-unavailable" if variant == "audit-fault" else "none",
                    "contains_business_content": False,
                }
                if observed["security_signal"] != expected_signal:
                    errors.append(f"{label}:SECURITY_SIGNAL_INVALID")
            finally:
                target.cleanup()
                try:
                    cleanup = target.audit_query_cleanup_state()
                    if cleanup != {"namespace_present": False, "audit_events": 0,
                                   "query_receipts": 0, "cached_results": 0}:
                        errors.append(f"{surface}/{variant}:AUDIT_QUERY_CLEANUP_RESIDUAL")
                except Exception:
                    errors.append(f"{surface}/{variant}:AUDIT_QUERY_CLEANUP_OBSERVATION_ERROR")
    if len(observations) != len(surfaces) * len(variants):
        errors.append("INCOMPLETE_AUDIT_QUERY_COVERAGE")
    return _case("E-AUD-004", observations, errors)


def _approval_fixture(root: Path) -> dict[str, Any]:
    value = load_fixture(root, "proposal-approval.synthetic.json", "proposal-approval-binding")
    if len(value["data"].get("proposals", [])) != 1 or len(value["data"].get("approval_requests", [])) != 1:
        raise ValueError("approval fixture is incomplete")
    return value


def _approval_surface(target: SecurityTarget, root: Path) -> dict[str, Any]:
    fixture = _approval_fixture(root)
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    target.prepare(copy.deepcopy(fixture))
    try:
        catalogs = target.catalogs()
        registered: set[str] = set()
        if not isinstance(catalogs, dict) or set(catalogs) != {"tool", "skill", "mcp"}:
            errors.append("CATALOG_SHAPE")
        else:
            for kind, descriptors in catalogs.items():
                if not isinstance(descriptors, list):
                    errors.append(f"{kind}:CATALOG_SHAPE")
                    continue
                for descriptor in descriptors:
                    if not isinstance(descriptor, dict) or set(descriptor) != CAPABILITY_FIELDS:
                        errors.append(f"{kind}:UNKNOWN_CAPABILITY_METADATA")
                        continue
                    capability_id = descriptor["capability_id"]
                    if not isinstance(capability_id, str) or not capability_id or capability_id in registered:
                        errors.append(f"{kind}:INVALID_OR_DUPLICATE_CAPABILITY_ID")
                        continue
                    registered.add(capability_id)
                    if (
                        descriptor["operation_family"] not in ("query", "draft")
                        or descriptor["side_effect"] not in ("none", "ephemeral-draft")
                        or descriptor["risk_floor"] not in ("Q", "D")
                        or any(descriptor[field] != "none" for field in (
                            "proposal_effect", "approval_effect", "receipt_effect"
                        ))
                        or not isinstance(descriptor["schema_sha256"], str)
                        or len(descriptor["schema_sha256"]) != 64
                        or any(character not in "0123456789abcdef" for character in descriptor["schema_sha256"])
                    ):
                        errors.append(f"{kind}:{capability_id}:MUTATING_CAPABILITY_EXPOSED")
        for alias in sorted(registered | set(APPROVAL_TOOL_ALIASES)):
            try:
                observed = target.agent_tool_attempt(alias)
            except Exception:
                errors.append(f"{alias}:TARGET_ERROR")
                continue
            observations.append(observed)
            if not _closed_result(
                observed,
                {"status", "proposal_consumed", "approval_state_changes",
                 "approval_receipts_minted", "business_writes", "audit_action"},
                bool_fields=("proposal_consumed",),
                int_fields=("approval_state_changes", "approval_receipts_minted", "business_writes"),
            ):
                errors.append(f"{alias}:TOOL_OBSERVATION_INVALID")
                continue
            if (
                observed["proposal_consumed"] is not False
                or observed["approval_state_changes"] != 0
                or observed["approval_receipts_minted"] != 0
                or observed["business_writes"] != 0
                or observed["audit_action"] == "approval.consumed"
            ):
                errors.append(f"{alias}:AGENT_APPROVAL_BYPASS")
            if alias in APPROVAL_TOOL_ALIASES and (
                observed["status"] not in ("forbidden", "unknown")
                or observed["audit_action"] != "tool.denied"
            ):
                errors.append(f"{alias}:FORGED_APPROVAL_ALIAS_NOT_DENIED")
    finally:
        target.cleanup()
    if len(observations) != len(registered | set(APPROVAL_TOOL_ALIASES)):
        errors.append("INCOMPLETE_ALIAS_COVERAGE")
    return _case("E-AGT-015", observations, errors)


def _approval_binding(target: SecurityTarget, root: Path, eval_id: str) -> dict[str, Any]:
    fixture = _approval_fixture(root)
    sequences = (
        tuple((variant,) for variant in (
            "foreign-session", "foreign-client", "wrong-proposal-hash",
            "wrong-resource-version", "expired", "csrf-mismatch",
        ))
        if eval_id == "E-AGT-018" else
        (
            ("matching-trusted-ui-first", "duplicate-click"),
            ("rejected", "rejected-replay"),
            ("expired", "expired-replay"),
            ("matching-trusted-ui-first", "cross-command-replay"),
            ("background-without-trusted-binding",),
        )
    )
    observations: list[dict[str, Any]] = []
    errors: list[str] = []
    proposal_id = fixture["data"]["proposals"][0]["proposal_id"]
    receipt_id = fixture["data"]["approval_requests"][0]["approval_request_id"]
    for sequence in sequences:
        target.prepare(copy.deepcopy(fixture))
        try:
            expected_total = 0
            for variant in sequence:
                try:
                    observed = target.approval_attempt(variant, fixture)
                except Exception:
                    errors.append(f"{variant}:TARGET_ERROR")
                    continue
                observations.append(observed)
                accepted = variant == "matching-trusted-ui-first"
                expected_total += int(accepted)
                if (
                    not _closed_result(
                        observed,
                        {"accepted", "consumption_count", "total_consumptions", "business_writes",
                         "proposal_id", "receipt_id", "audit_action"},
                        bool_fields=("accepted",),
                        int_fields=("consumption_count", "total_consumptions", "business_writes"),
                    )
                    or observed.get("accepted") is not accepted
                    or observed.get("consumption_count") != int(accepted)
                    or observed.get("total_consumptions") != expected_total
                    or observed.get("business_writes") != int(accepted)
                    or observed.get("proposal_id") != proposal_id
                    or observed.get("receipt_id") != receipt_id
                    or observed.get("audit_action") != ("approval.consumed" if accepted else "approval.denied")
                ):
                    errors.append(f"{variant}:APPROVAL_BINDING_OR_REPLAY")
        finally:
            target.cleanup()
    if len(observations) != sum(len(sequence) for sequence in sequences):
        errors.append("INCOMPLETE_APPROVAL_VARIANTS")
    return _case(eval_id, observations, errors)


def _risk_command(**changes: Any) -> dict[str, Any]:
    command = {
        "risk_policy_version": "r1.0", "command": "record.create", "object_type": "record", "kind": "praise",
        "data_class": "D2", "affected_count": 1, "attachment": False,
        "external": False, "irreversible": False,
    }
    command.update(changes)
    return command


def _validate_risk_policy(root: Path) -> None:
    raw = (root / POLICY_RELATIVE_PATH).read_bytes()
    # The repository permits Windows CRLF checkout; pin logical LF bytes.
    if hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() != POLICY_SHA256:
        raise ValueError("candidate risk policy definition drift")
    value = json.loads(raw)
    if (
        value.get("schema") != "class-os.synthetic-risk-policy-definition/v1"
        or value.get("version") != "r1.0"
        or value.get("status") != "candidate-eval-contract-not-production-approval"
        or value.get("command_floor") != {
            "class.create": "W2", "student.create": "W1", "record.create": "W1",
            "record.correct": "W2", "task.create": "W1", "exit_export.create": "W2",
        }
        or value.get("forbidden_r1_commands") != ["record.delete", "student.delete", "message.send"]
    ):
        raise ValueError("candidate risk policy definition invalid")


RISK_CASES: dict[str, tuple[dict[str, Any], str, str, bool]] = {
    "E-RISK-001": (_risk_command(), "allow", "W1", False),
    "E-RISK-002": (_risk_command(kind="discipline", data_class="D3"), "allow", "W2", False),
    "E-RISK-003": (_risk_command(data_class="D4"), "reject", "W2", False),
    "E-RISK-004": (_risk_command(affected_count=2), "allow", "W2", False),
    "E-RISK-005": (_risk_command(external=True), "reject", "X", True),
}


def _risk_policy(target: SecurityTarget, eval_id: str) -> dict[str, Any]:
    command, expected_decision, expected_risk, recent_auth = RISK_CASES[eval_id]
    errors: list[str] = []
    observations: list[dict[str, Any]] = []
    try:
        baseline = target.evaluate_risk(_risk_command())
        if (
            not _closed_result(baseline, {"decision", "risk", "requires_recent_reauth",
                                          "policy_version", "policy_sha256"},
                               bool_fields=("requires_recent_reauth",))
            or baseline.get("decision") != "allow"
            or baseline.get("risk") != "W1"
            or baseline.get("policy_version") != "r1.0"
            or baseline.get("policy_sha256") != POLICY_SHA256
        ):
            errors.append("BASELINE_RISK_MISMATCH")
    except Exception:
        baseline = None
        errors.append("BASELINE_TARGET_ERROR")
    variants = [(command, expected_decision, expected_risk, recent_auth)]
    if eval_id in ("E-RISK-002", "E-RISK-004"):
        variants.append((_risk_command(data_class="D3", affected_count=2), "allow", "W2", False))
    if eval_id == "E-RISK-002":
        variants.append((_risk_command(data_class="D3", client_claimed_risk="W1"), "allow", "W2", False))
    if eval_id == "E-RISK-003":
        variants.append((_risk_command(attachment=True), "reject", "W2", False))
        variants.append((_risk_command(data_class="D4", irreversible=True), "reject", "X", True))
    if eval_id == "E-RISK-005":
        variants.append((_risk_command(irreversible=True), "reject", "X", True))
        variants.append((_risk_command(external=True, affected_count=2), "reject", "X", True))
        variants.extend((
            (_risk_command(command="class.create", object_type="class"), "allow", "W2", False),
            (_risk_command(command="student.create", object_type="student"), "allow", "W1", False),
            (_risk_command(command="task.create", object_type="task"), "allow", "W1", False),
            (_risk_command(command="record.correct"), "allow", "W2", False),
            (_risk_command(command="exit_export.create", object_type="exit_export"), "allow", "W2", False),
            (_risk_command(command="record.create", kind="talk"), "allow", "W2", False),
            (_risk_command(command="record.delete", irreversible=False), "reject", "X", True),
            (_risk_command(command="student.delete", object_type="student", irreversible=False),
             "reject", "X", True),
            (_risk_command(command="message.send", object_type="message", external=False),
             "reject", "X", True),
            (_risk_command(object_type="student"), "reject", "X", True),
        ))
        for data_class, count, attachment, external, irreversible in product(
            ("D2", "D3", "D4"), (1, 2), (False, True), (False, True), (False, True)
        ):
            elevated = external or irreversible
            forbidden = elevated or attachment or data_class == "D4"
            risk = "X" if elevated else "W2" if forbidden or data_class == "D3" or count > 1 else "W1"
            variants.append((
                _risk_command(data_class=data_class, affected_count=count,
                              attachment=attachment, external=external,
                              irreversible=irreversible),
                "reject" if forbidden else "allow", risk, elevated,
            ))
    for index, (payload, decision, floor, requires_reauth) in enumerate(variants):
        try:
            observed = target.evaluate_risk(copy.deepcopy(payload))
        except Exception:
            errors.append(f"variant-{index}:TARGET_ERROR")
            continue
        observations.append(observed)
        if (
            not _closed_result(observed, {"decision", "risk", "requires_recent_reauth",
                                          "policy_version", "policy_sha256"},
                               bool_fields=("requires_recent_reauth",))
            or observed.get("decision") != decision
            or observed.get("risk") != floor
            or observed.get("requires_recent_reauth") is not requires_reauth
            or observed.get("policy_version") != "r1.0"
            or observed.get("policy_sha256") != POLICY_SHA256
        ):
            errors.append(f"variant-{index}:RISK_POLICY_MISMATCH")
        if (
            isinstance(baseline, dict)
            and isinstance(observed, dict)
            and isinstance(observed.get("risk"), str)
            and RISK_RANK.get(observed["risk"], 0) < RISK_RANK.get(baseline.get("risk"), 0)
        ):
            errors.append(f"variant-{index}:RISK_DOWNGRADE")
    if len(observations) != len(variants):
        errors.append("INCOMPLETE_RISK_VARIANTS")
    try:
        unsupported = target.evaluate_risk(_risk_command(risk_policy_version="unknown"))
        if (
            not _closed_result(unsupported, {"decision", "risk", "requires_recent_reauth",
                                             "policy_version", "policy_sha256"},
                               bool_fields=("requires_recent_reauth",))
            or unsupported != {"decision": "reject", "risk": "UNCLASSIFIED",
                               "requires_recent_reauth": False,
                               "policy_version": None, "policy_sha256": None}
        ):
            errors.append("UNKNOWN_POLICY_VERSION_ACCEPTED")
    except Exception:
        errors.append("UNKNOWN_POLICY_VERSION_TARGET_ERROR")
    return _case(eval_id, observations, errors)


def run_selected(target: SecurityTarget, *, ids: set[str], root: Path = ROOT) -> list[dict[str, Any]]:
    if not ids or not ids.issubset(SUPPORTED):
        raise ValueError("security eval selection contains an unknown or empty id")
    if any(eval_id.startswith("E-RISK-") for eval_id in ids):
        _validate_risk_policy(root)
    cases = {
        "E-AUTH-001": _workspace_isolation,
        "E-AUTH-003": _server_side_authorization,
        "E-AUD-001": _audit_unavailable,
        "E-AUD-002": lambda selected, selected_root: _audit_unavailable(
            selected, selected_root, eval_id="E-AUD-002"
        ),
        "E-AUD-003": _export_audit_failure,
        "E-AUD-004": _audit_query,
        "E-AGT-015": _approval_surface,
        "E-AGT-018": lambda selected, selected_root: _approval_binding(selected, selected_root, "E-AGT-018"),
        "E-AGT-020": lambda selected, selected_root: _approval_binding(selected, selected_root, "E-AGT-020"),
    }
    return [
        _risk_policy(target, eval_id) if eval_id.startswith("E-RISK-") else cases[eval_id](target, root)
        for eval_id in sorted(ids)
    ]


def run_cli(*, root: Path = ROOT) -> dict[str, Any]:
    # No production adapter is present. A passing fake must never promote eval state.
    return {
        "schema": "class-os.security-eval-runner/v1",
        "status": "target-unavailable",
        "eval_ids": sorted(SUPPORTED),
        "implemented_green": False,
        "reason": "No production API/Query Gateway and durable-audit observation adapter is bound.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run",))
    args = parser.parse_args()
    if args.command == "run":
        print(json.dumps(run_cli(), ensure_ascii=False, sort_keys=True))
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
