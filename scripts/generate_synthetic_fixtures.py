#!/usr/bin/env python3
"""Generate deterministic, synthetic-only Release 1 evaluation fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SEED = 20260921
FIXED_CLOCK = "2026-09-01T08:00:00+08:00"
SCHEMA = "class-os.synthetic-fixture/v1"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "evals/class-os-v1/fixtures/r1"


class FixtureError(RuntimeError):
    """A deterministic fixture generation or verification failure."""


@dataclass(frozen=True)
class SensitiveFinding:
    file: str
    pattern: str


SENSITIVE_PATTERNS = {
    "cn_mobile": re.compile(rb"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "cn_identity": re.compile(rb"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    "secret_token": re.compile(rb"(?:sk|ghp|github_pat)[-_][A-Za-z0-9_-]{12,}"),
}


def _id(seed: int, label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"class-os-synthetic:{seed}:{label}"))


def _meta(seed: int, purpose: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "synthetic": True,
        "seed": seed,
        "clock": FIXED_CLOCK,
        "purpose": purpose,
        "provenance": "deterministic-fixture-factory",
        "contains_real_person_data": False,
    }


def build_fixture_bundle(seed: int = DEFAULT_SEED) -> dict[str, Any]:
    workspace_a = {
        "workspace_id": _id(seed, "workspace-a"),
        "owner_id": _id(seed, "owner-a"),
        "label": "合成工作区甲",
    }
    workspace_b = {
        "workspace_id": _id(seed, "workspace-b"),
        "owner_id": _id(seed, "owner-b"),
        "label": "合成工作区乙",
    }
    class_a = {
        "class_id": _id(seed, "class-a"),
        "workspace_id": workspace_a["workspace_id"],
        "display_name": "合成七年级甲班",
        "version": 1,
    }
    class_b = {
        "class_id": _id(seed, "class-b"),
        "workspace_id": workspace_b["workspace_id"],
        "display_name": "合成七年级甲班",
        "version": 1,
    }
    term_a = {
        "term_id": _id(seed, "term-a"),
        "workspace_id": workspace_a["workspace_id"],
        "label": "合成学期甲",
        "valid_from": "2026-09-01",
        "valid_to": "2027-02-01",
    }
    term_b = {
        "term_id": _id(seed, "term-b"),
        "workspace_id": workspace_b["workspace_id"],
        "label": "合成学期甲",
        "valid_from": "2026-09-01",
        "valid_to": "2027-02-01",
    }
    students = [
        {
            "student_id": _id(seed, "student-a-1"),
            "workspace_id": workspace_a["workspace_id"],
            "class_id": class_a["class_id"],
            "term_id": term_a["term_id"],
            "display_name": "合成学生甲",
            "status": "active",
            "version": 1,
        },
        {
            "student_id": _id(seed, "student-a-2"),
            "workspace_id": workspace_a["workspace_id"],
            "class_id": class_a["class_id"],
            "term_id": term_a["term_id"],
            "display_name": "合成学生乙",
            "status": "active",
            "version": 1,
        },
        {
            "student_id": _id(seed, "student-b-1"),
            "workspace_id": workspace_b["workspace_id"],
            "class_id": class_b["class_id"],
            "term_id": term_b["term_id"],
            "display_name": "合成学生甲",
            "status": "active",
            "version": 1,
        },
    ]
    student_identifiers = [
        {
            "identifier_id": _id(seed, "identifier-a-1-school"),
            "student_id": students[0]["student_id"],
            "authority": "synthetic-school-a",
            "type": "school_number",
            "value": "SYN-A-0001",
            "valid_from": "2026-09-01",
            "valid_to": None,
        },
        {
            "identifier_id": _id(seed, "identifier-a-1-exam"),
            "student_id": students[0]["student_id"],
            "authority": "synthetic-exam-a",
            "type": "exam_number",
            "value": "EX-A-0101",
            "valid_from": "2026-09-01",
            "valid_to": None,
        },
        {
            "identifier_id": _id(seed, "identifier-a-2-conflict"),
            "student_id": students[1]["student_id"],
            "authority": "synthetic-school-a",
            "type": "school_number",
            "value": "SYN-A-0001",
            "valid_from": "2026-09-01",
            "valid_to": None,
            "expected_resolution": "duplicate_candidate_no_merge",
        },
    ]
    correlation_id = _id(seed, "correlation-fact-loop")
    records = [
        {
            "record_id": _id(seed, "record-late"),
            "workspace_id": workspace_a["workspace_id"],
            "student_id": students[0]["student_id"],
            "kind": "attendance_late_fact",
            "occurred_at": "2026-09-01T07:55:00+08:00",
            "recorded_at": FIXED_CLOCK,
            "source": "trusted-ui-synthetic",
            "correlation_id": correlation_id,
            "version": 1,
        },
        {
            "record_id": _id(seed, "record-homework-missing"),
            "workspace_id": workspace_a["workspace_id"],
            "student_id": students[1]["student_id"],
            "kind": "homework_missing_fact",
            "occurred_at": "2026-09-01T07:50:00+08:00",
            "recorded_at": "2026-09-01T08:01:00+08:00",
            "source": "trusted-ui-synthetic",
            "correlation_id": correlation_id,
            "version": 1,
        },
        {
            "record_id": _id(seed, "record-homework-submitted"),
            "workspace_id": workspace_a["workspace_id"],
            "student_id": students[1]["student_id"],
            "kind": "homework_submitted_fact",
            "occurred_at": "2026-09-01T09:05:00+08:00",
            "recorded_at": "2026-09-01T09:06:00+08:00",
            "source": "trusted-ui-synthetic",
            "corrects_or_follows": _id(seed, "record-homework-missing"),
            "correlation_id": correlation_id,
            "version": 1,
        },
    ]
    tasks = [
        {
            "task_id": _id(seed, "task-follow-up"),
            "workspace_id": workspace_a["workspace_id"],
            "source_ref": records[0]["record_id"],
            "state": "open",
            "responsibility_state": "owner_confirmed",
            "due_at": "2026-09-01T17:00:00+08:00",
            "version": 1,
        }
    ]
    proposal_hash = hashlib.sha256(
        json.dumps(
            {"record_id": records[0]["record_id"], "expected_version": 1},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    proposals = [
        {
            "proposal_id": _id(seed, "proposal-a"),
            "workspace_id": workspace_a["workspace_id"],
            "actor_id": workspace_a["owner_id"],
            "target_ref": records[0]["record_id"],
            "risk": "W2",
            "proposal_hash": proposal_hash,
            "state": "pending",
            "expires_at": "2026-09-01T08:15:00+08:00",
        }
    ]
    approval_requests = [
        {
            "approval_request_id": _id(seed, "approval-request-a"),
            "proposal_id": proposals[0]["proposal_id"],
            "session_id": _id(seed, "session-a"),
            "client_id": _id(seed, "client-a"),
            "csrf_nonce": "synthetic-nonce-a",
            "expected_outcome": "consume_once_if_all_bindings_match",
        }
    ]
    audit_events = [
        {
            "audit_event_id": _id(seed, "audit-record-create"),
            "workspace_id": workspace_a["workspace_id"],
            "actor_id": workspace_a["owner_id"],
            "action": "record.create.synthetic",
            "resource_ref": records[0]["record_id"],
            "correlation_id": correlation_id,
            "occurred_at": FIXED_CLOCK,
            "payload_included": False,
        },
        {
            "audit_event_id": _id(seed, "audit-failure"),
            "workspace_id": workspace_a["workspace_id"],
            "actor_id": workspace_a["owner_id"],
            "action": "student.read.synthetic",
            "resource_ref": students[0]["student_id"],
            "correlation_id": _id(seed, "correlation-audit-failure"),
            "occurred_at": "2026-09-01T08:02:00+08:00",
            "fault": "durable_audit_unavailable",
            "expected_outcome": "fail_closed_before_response",
            "payload_included": False,
        },
    ]
    return {
        "meta": _meta(seed, "canonical-r1-eval-bundle"),
        "workspace_a": workspace_a,
        "workspace_b": workspace_b,
        "classes": [class_a, class_b],
        "terms": [term_a, term_b],
        "students": students,
        "student_identifiers": student_identifiers,
        "records": records,
        "tasks": tasks,
        "proposals": proposals,
        "approval_requests": approval_requests,
        "audit_events": audit_events,
    }


def _document(seed: int, purpose: str, data: Mapping[str, Any]) -> dict[str, Any]:
    return {"meta": _meta(seed, purpose), "data": data}


def render_fixture_files(seed: int = DEFAULT_SEED) -> dict[str, bytes]:
    bundle = build_fixture_bundle(seed)
    documents = {
        "canonical-r1.synthetic.json": bundle,
        "workspace-isolation.synthetic.json": _document(
            seed,
            "workspace-isolation",
            {
                "workspaces": [bundle["workspace_a"], bundle["workspace_b"]],
                "classes": bundle["classes"],
                "students": [bundle["students"][0], bundle["students"][2]],
                "cross_workspace_expected_outcome": "forbidden_not_found_safe",
            },
        ),
        "student-identifier.synthetic.json": _document(
            seed,
            "student-identifier-conflict",
            {
                "students": bundle["students"][:2],
                "identifiers": bundle["student_identifiers"],
            },
        ),
        "fact-events.synthetic.json": _document(
            seed,
            "fact-event-task-timeline",
            {
                "students": bundle["students"][:2],
                "records": bundle["records"],
                "tasks": bundle["tasks"],
            },
        ),
        "proposal-approval.synthetic.json": _document(
            seed,
            "proposal-approval-binding",
            {
                "proposals": bundle["proposals"],
                "approval_requests": bundle["approval_requests"],
            },
        ),
        "audit-failure.synthetic.json": _document(
            seed,
            "audit-fail-closed",
            {"audit_events": bundle["audit_events"], "projection_release_expected": False},
        ),
    }
    rendered: dict[str, bytes] = {}
    for name, document in documents.items():
        rendered[name] = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    return rendered


def scan_for_sensitive_patterns(files: Mapping[str, bytes]) -> list[SensitiveFinding]:
    findings: list[SensitiveFinding] = []
    for name, content in sorted(files.items()):
        for pattern_name, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(content):
                findings.append(SensitiveFinding(file=name, pattern=pattern_name))
    return findings


def _assert_no_sensitive_findings(files: Mapping[str, bytes]) -> None:
    findings = scan_for_sensitive_patterns(files)
    if findings:
        summary = ", ".join(f"{finding.file}:{finding.pattern}" for finding in findings)
        raise FixtureError(f"synthetic fixture sensitive-pattern findings: {summary}")


def write_fixture_directory(output_dir: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    files = render_fixture_files(seed)
    _assert_no_sensitive_findings(files)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output_dir / name).write_bytes(content)
    return {
        "seed": seed,
        "file_count": len(files),
        "sha256": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())},
    }


def check_fixture_directory(output_dir: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    expected = render_fixture_files(seed)
    _assert_no_sensitive_findings(expected)
    actual_names = {path.name for path in output_dir.glob("*.json") if path.is_file()}
    expected_names = set(expected)
    if actual_names != expected_names:
        raise FixtureError(
            f"fixture file-set drift; missing={sorted(expected_names - actual_names)}, "
            f"extra={sorted(actual_names - expected_names)}"
        )
    drift = [name for name, content in expected.items() if (output_dir / name).read_bytes() != content]
    if drift:
        raise FixtureError(f"fixture content drift: {', '.join(sorted(drift))}")
    _assert_no_sensitive_findings({name: (output_dir / name).read_bytes() for name in actual_names})
    return {
        "seed": seed,
        "file_count": len(expected),
        "sha256": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(expected.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = write_fixture_directory(args.output_dir, args.seed)
        else:
            result = check_fixture_directory(args.output_dir, args.seed)
    except FixtureError as exc:
        print(f"FIXTURE ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
