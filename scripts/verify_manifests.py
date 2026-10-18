#!/usr/bin/env python3
"""Strict, read-only validation for Class OS release manifests.

The `task-graph` command implements T-REVAL-020's source-row hashes, explicit
task DAG, transitive closure and definition/run-state separation.  Because no
concrete external evidence adapter is wired into this command yet, completion
and implemented-green claims fail closed instead of being counted as verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml


class ManifestError(RuntimeError):
    """A deterministic release-definition validation failure."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ManifestError(f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


REQUIREMENT_RE = re.compile(r"\b(?:FR|NFR)-[A-Z]+-\d{3}\b")
EVAL_RE = re.compile(r"\bE-[A-Z0-9]+-\d{3}\b")
TASK_RE = re.compile(r"\bT-R[A-Z]+-\d{3}\b")
CASE_ROW_RE = re.compile(r"^\|\s*(E-[A-Z0-9]+-\d{3})\s*\|")
EX_HEADING_RE = re.compile(r"^##\s+(EX-R1-\d{3})\b", re.MULTILINE)
FIELD_RE = re.compile(r"^-\s+([a-z_]+):\s*(.*)$", re.MULTILINE)

EVAL_ROOT_KEYS = {
    "schema_version",
    "release",
    "artifact_role",
    "run_state_manifest",
    "approval_state",
    "signature_policy",
    "policy",
    "run_state_contract",
    "required_before_enum",
    "selector_semantics",
    "required_evals",
    "requirement_coverage",
}
EVAL_ENTRY_KEYS = {
    "eval_id",
    "applicable",
    "reason",
    "spec_status",
    "runner",
    "required_before",
    "evidence",
}
REQUIREMENTS_ROOT_KEYS = {
    "schema_version",
    "release",
    "artifact_role",
    "source",
    "approval_state",
    "signature_policy",
    "policy",
    "included",
    "excluded",
}
TASK_ROOT_KEYS = {
    "schema_version",
    "release",
    "artifact_role",
    "source",
    "state_manifest",
    "approval_state",
    "signature_policy",
    "policy",
    "task_body_hash_contract",
    "task_definitions",
}
TASK_ENTRY_KEYS = {
    "task_id",
    "source_line",
    "effort_days",
    "goal",
    "depends_on",
    "requirement_ids",
    "rule_ids",
    "eval_ids",
    "task_body_sha256",
}
TASK_STATE_ROOT_KEYS = {
    "schema_version",
    "release",
    "artifact_role",
    "definition_manifest",
    "definition_sha256",
    "definition_bundle_sha256",
    "target_release_digest",
    "target_commit",
    "signature_policy",
    "default_status",
    "tasks",
    "state_transition_artifact",
}
TASK_STATE_ENTRY_KEYS = {"task_id", "status", "target_commit", "evidence"}
EVAL_STATE_ROOT_KEYS = {
    "schema_version",
    "release",
    "artifact_role",
    "definition_manifest",
    "definition_sha256",
    "target_release_digest",
    "target_commit",
    "default_run_status",
    "default_evidence",
    "overrides",
    "signature_policy",
    "state_transition_artifact",
}
EVAL_STATE_ENTRY_KEYS = {"eval_id", "status", "evidence"}
RELEASE_GATE_ROOT_KEYS = {
    "schema_version",
    "release",
    "artifact_role",
    "state_manifest",
    "approval_state",
    "signature_policy",
    "task_definition_manifest",
    "task_state_manifest",
    "eval_definition_manifest",
    "eval_state_manifest",
    "global_conditions",
    "before_feature_task",
    "before_release_candidate",
    "before_pilot_readiness",
    "before_any_real_write",
    "on_admission_expiry_revocation_report_or_scope_mismatch",
}
REQUIRED_EX_FIELDS = {
    "eval_id",
    "owner",
    "runner_mapping",
    "setup",
    "input_fixture",
    "oracle",
    "cleanup",
}
TASK_SOURCE_ROW_RE = re.compile(r"^\|\s*(T-R[A-Z]+-\d{3})\s*/\s*(\d+)d(?:\s+[^|]+)?\s*\|")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ManifestError(f"required file is missing: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ManifestError(f"file is not strict UTF-8: {path}") from exc


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(_read_text(path), Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"YAML root must be a mapping: {path}")
    return value


def _expect_keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ManifestError(f"{context} has unknown keys: {', '.join(unknown)}")


def _expect_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    _expect_keys(value, expected, context)
    missing = sorted(expected - set(value))
    if missing:
        raise ManifestError(f"{context} is missing keys: {', '.join(missing)}")


def _expect_identity(value: dict[str, Any], expected: dict[str, Any], context: str) -> None:
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ManifestError(
                f"{context} {field} must be {expected_value!r}, got {value.get(field)!r}"
            )


def _expect_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{context} must be a list")
    return value


def _expect_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{context} must be a mapping")
    return value


def _unique_ids(values: Iterable[str], kind: str) -> set[str]:
    values = list(values)
    duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ManifestError(f"duplicate {kind}: {', '.join(duplicates)}")
    return set(values)


def _expand_eval_expression(expression: str) -> set[str]:
    """Expand the compact notation used only by executable-spec prose."""
    result: set[str] = set()
    for comma_part in (part.strip() for part in expression.split(",")):
        if not comma_part:
            continue
        slash_parts = [part.strip() for part in comma_part.split("/")]
        first = slash_parts[0]
        match = re.fullmatch(r"(E-[A-Z0-9]+-)(\d{3})(?:[—-](\d{3}))?", first)
        if not match:
            raise ManifestError(f"invalid executable eval expression: {comma_part}")
        prefix, start, end = match.group(1), match.group(2), match.group(3)
        segments = [(start, end)]
        for segment in slash_parts[1:]:
            short_match = re.fullmatch(r"(\d{3})(?:[—-](\d{3}))?", segment)
            if not short_match:
                raise ManifestError(f"invalid executable eval shorthand: {comma_part}")
            segments.append((short_match.group(1), short_match.group(2)))
        for segment_start, segment_end in segments:
            start_number = int(segment_start)
            end_number = int(segment_end or segment_start)
            if end_number < start_number:
                raise ManifestError(f"reversed executable eval range: {comma_part}")
            result.update(f"{prefix}{number:03d}" for number in range(start_number, end_number + 1))
    return result


def _parse_executable_specs(path: Path) -> tuple[set[str], set[str], int]:
    text = _read_text(path)
    headings = list(EX_HEADING_RE.finditer(text))
    if len(headings) < 22:
        raise ManifestError(f"expected at least 22 executable containers, found {len(headings)}")
    executable_ids: set[str] = set()
    pending_ids: set[str] = set()
    seen_containers: set[str] = set()
    for index, heading in enumerate(headings):
        container_id = heading.group(1)
        if container_id in seen_containers:
            raise ManifestError(f"duplicate executable container: {container_id}")
        seen_containers.add(container_id)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[heading.end() : end]
        fields = dict(FIELD_RE.findall(block))
        missing = sorted(REQUIRED_EX_FIELDS - set(fields))
        if missing:
            raise ManifestError(f"{container_id} missing executable fields: {', '.join(missing)}")
        executable_ids.update(_expand_eval_expression(fields["eval_id"]))
        if "covered_cases_pending_runner" in fields:
            pending_ids.update(_expand_eval_expression(fields["covered_cases_pending_runner"]))
    overlap = executable_ids & pending_ids
    if overlap:
        raise ManifestError(
            "evals cannot be executable and pending in the same definition: " + ", ".join(sorted(overlap))
        )
    return executable_ids, pending_ids, len(headings)


def _parse_case_catalog(cases_dir: Path) -> tuple[set[str], dict[str, str]]:
    case_ids: list[str] = []
    explicit_maturity: dict[str, str] = {}
    for path in sorted(cases_dir.glob("*.md")):
        lines = _read_text(path).splitlines()
        headers: list[str] | None = None
        for line in lines:
            if line.startswith("| eval_id |"):
                headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
                continue
            match = CASE_ROW_RE.match(line)
            if not match or headers is None:
                continue
            eval_id = match.group(1)
            case_ids.append(eval_id)
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            for column in ("spec_status", "maturity"):
                if column in headers and len(cells) > headers.index(column):
                    explicit_maturity[eval_id] = cells[headers.index(column)]
    # Future E-EVO cases are a separate universe and may be ignored by R1.
    r1_case_ids = [eval_id for eval_id in case_ids if not eval_id.startswith("E-EVO-")]
    duplicates = sorted(item for item, count in Counter(r1_case_ids).items() if count > 1)
    if duplicates:
        raise ManifestError(f"duplicate R1 case eval_id: {', '.join(duplicates)}")
    return set(r1_case_ids), explicit_maturity


def validate_eval_meta(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    manifest_path = repo_root / ".ai/gates/release-1-evals.yaml"
    manifest = _load_yaml(manifest_path)
    _expect_keys(manifest, EVAL_ROOT_KEYS, "release-1-evals root")
    if manifest.get("release") != "class-os-r1":
        raise ManifestError("release-1-evals release must be class-os-r1")

    stages = _expect_list(manifest.get("required_before_enum"), "required_before_enum")
    if not stages or any(not isinstance(stage, str) or not stage for stage in stages):
        raise ManifestError("required_before_enum must contain non-empty strings")
    stage_set = _unique_ids(stages, "required_before value")

    entries = _expect_list(manifest.get("required_evals"), "required_evals")
    eval_ids: list[str] = []
    status_by_id: dict[str, str] = {}
    allowed_statuses = set(
        _expect_list(
            _expect_mapping(manifest.get("policy"), "eval policy").get("spec_status_allowed_values"),
            "spec_status_allowed_values",
        )
    )
    for index, raw_entry in enumerate(entries):
        entry = _expect_mapping(raw_entry, f"required_evals[{index}]")
        _expect_keys(entry, EVAL_ENTRY_KEYS, f"required_evals[{index}]")
        missing = sorted(EVAL_ENTRY_KEYS - set(entry))
        if missing:
            raise ManifestError(f"required_evals[{index}] missing keys: {', '.join(missing)}")
        eval_id = entry["eval_id"]
        if not isinstance(eval_id, str) or not EVAL_RE.fullmatch(eval_id):
            raise ManifestError(f"invalid eval_id at required_evals[{index}]: {eval_id!r}")
        eval_ids.append(eval_id)
        required_before = entry["required_before"]
        if required_before not in stage_set:
            raise ManifestError(f"{eval_id} has unknown required_before: {required_before!r}")
        status = entry["spec_status"]
        if status not in allowed_statuses:
            raise ManifestError(f"{eval_id} has invalid spec_status: {status!r}")
        if entry["evidence"] is not None:
            raise ManifestError(f"{eval_id} inline evidence must remain null")
        status_by_id[eval_id] = status
    eval_set = _unique_ids(eval_ids, "eval_id")

    executable_ids, pending_ids, container_count = _parse_executable_specs(
        repo_root / "evals/class-os-v1/executable/release-1-p0.md"
    )
    declared_executable = {eval_id for eval_id, status in status_by_id.items() if status == "executable-spec"}
    if executable_ids != declared_executable:
        missing = sorted(declared_executable - executable_ids)
        extra = sorted(executable_ids - declared_executable)
        raise ManifestError(
            f"R1 maturity drift between eval manifest and executable specs; missing={missing}, extra={extra}"
        )
    if any(status_by_id[eval_id] != "catalogued" for eval_id in pending_ids & eval_set):
        raise ManifestError("pending executable cases must remain catalogued")

    case_ids, explicit_maturity = _parse_case_catalog(repo_root / "evals/class-os-v1/cases")
    unknown_pending = sorted(pending_ids - case_ids)
    if unknown_pending:
        raise ManifestError(f"pending executable cases are absent from the case catalog: {unknown_pending}")
    missing_cases = sorted(eval_set - case_ids)
    if missing_cases:
        raise ManifestError(f"required evals missing from case catalog: {', '.join(missing_cases)}")
    for eval_id, maturity in explicit_maturity.items():
        if eval_id in status_by_id and status_by_id[eval_id] != maturity:
            raise ManifestError(
                f"R1 case maturity drift for {eval_id}: manifest={status_by_id[eval_id]}, case={maturity}"
            )
    for entry in entries:
        eval_id = entry["eval_id"]
        status = entry["spec_status"]
        if status == "catalogued" and entry["runner"] is not None:
            raise ManifestError(f"{eval_id} is catalogued but has a runner")
        if status == "executable-spec" and not entry["runner"]:
            raise ManifestError(f"{eval_id} is executable-spec but has no runner")

    return {
        "release": "class-os-r1",
        "required_eval_count": len(eval_set),
        "executable_spec_count": len(declared_executable),
        "catalogued_count": len(eval_set - declared_executable),
        "executable_container_count": container_count,
        "required_before_count": len(stage_set),
    }


def _validate_exact_scalar_references(
    value: Any,
    requirement_ids: set[str],
    eval_ids: set[str],
    task_ids: set[str],
    context: str,
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_exact_scalar_references(
                nested, requirement_ids, eval_ids, task_ids, f"{context}.{key}"
            )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_exact_scalar_references(
                nested, requirement_ids, eval_ids, task_ids, f"{context}[{index}]"
            )
    elif isinstance(value, str):
        if REQUIREMENT_RE.fullmatch(value) and value not in requirement_ids:
            raise ManifestError(f"unknown requirement reference {value} at {context}")
        if EVAL_RE.fullmatch(value) and value not in eval_ids:
            raise ManifestError(f"unknown eval reference {value} at {context}")
        if TASK_RE.fullmatch(value) and value not in task_ids:
            raise ManifestError(f"unknown task reference {value} at {context}")


def validate_gate_graph(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    gates = repo_root / ".ai/gates"
    requirements = _load_yaml(gates / "release-1-requirements.yaml")
    evals = _load_yaml(gates / "release-1-evals.yaml")
    tasks = _load_yaml(gates / "release-1-task-definitions.yaml")
    release_gates = _load_yaml(gates / "release-1-release-gates.yaml")
    _expect_keys(requirements, REQUIREMENTS_ROOT_KEYS, "release-1-requirements root")
    _expect_keys(evals, EVAL_ROOT_KEYS, "release-1-evals root")
    _expect_keys(tasks, TASK_ROOT_KEYS, "release-1-task-definitions root")
    _expect_keys(release_gates, RELEASE_GATE_ROOT_KEYS, "release-1-release-gates root")

    included_values = _expect_list(requirements.get("included"), "requirements included")
    if any(not isinstance(value, str) for value in included_values):
        raise ManifestError("requirements included must contain only IDs")
    included = _unique_ids(included_values, "included requirement")
    excluded = set(_expect_mapping(requirements.get("excluded"), "requirements excluded"))
    overlap = included & excluded
    if overlap:
        raise ManifestError(f"requirements both included and excluded: {', '.join(sorted(overlap))}")
    requirement_ids = included | excluded
    source_path = repo_root / str(requirements.get("source"))
    source_ids = set(REQUIREMENT_RE.findall(_read_text(source_path)))
    if requirement_ids != source_ids:
        raise ManifestError(
            f"requirement classification mismatch; missing={sorted(source_ids - requirement_ids)}, "
            f"extra={sorted(requirement_ids - source_ids)}"
        )

    eval_entries = _expect_list(evals.get("required_evals"), "required_evals")
    eval_ids = _unique_ids(
        [str(_expect_mapping(entry, "required eval").get("eval_id")) for entry in eval_entries],
        "eval_id",
    )
    coverage = _expect_mapping(evals.get("requirement_coverage"), "requirement_coverage")
    if set(coverage) != included:
        raise ManifestError(
            f"requirement coverage keys must equal included requirements; "
            f"missing={sorted(included - set(coverage))}, extra={sorted(set(coverage) - included)}"
        )
    for requirement_id, refs in coverage.items():
        refs = _expect_list(refs, f"requirement_coverage.{requirement_id}")
        if not refs:
            raise ManifestError(f"requirement_coverage.{requirement_id} must not be empty")
        unknown = sorted(set(refs) - eval_ids)
        if unknown:
            raise ManifestError(
                f"requirement_coverage.{requirement_id} has unknown eval reference: {', '.join(unknown)}"
            )

    task_entries = _expect_list(tasks.get("task_definitions"), "task_definitions")
    task_ids_list: list[str] = []
    for index, raw_entry in enumerate(task_entries):
        entry = _expect_mapping(raw_entry, f"task_definitions[{index}]")
        _expect_keys(entry, TASK_ENTRY_KEYS, f"task_definitions[{index}]")
        missing = sorted(TASK_ENTRY_KEYS - set(entry))
        if missing:
            raise ManifestError(f"task_definitions[{index}] missing keys: {', '.join(missing)}")
        task_id = entry["task_id"]
        if not isinstance(task_id, str) or not TASK_RE.fullmatch(task_id):
            raise ManifestError(f"invalid task_id at task_definitions[{index}]: {task_id!r}")
        task_ids_list.append(task_id)
    task_ids = _unique_ids(task_ids_list, "task_id")

    for index, raw_entry in enumerate(task_entries):
        entry = _expect_mapping(raw_entry, f"task_definitions[{index}]")
        task_id = entry["task_id"]
        unknown_dependencies = sorted(set(entry["depends_on"]) - task_ids)
        if unknown_dependencies:
            raise ManifestError(f"{task_id} has unknown task reference: {', '.join(unknown_dependencies)}")
        unknown_requirements = sorted(set(entry["requirement_ids"]) - requirement_ids)
        if unknown_requirements:
            raise ManifestError(
                f"{task_id} has unknown requirement reference: {', '.join(unknown_requirements)}"
            )
        unknown_evals = sorted(set(entry["eval_ids"]) - eval_ids)
        if unknown_evals:
            raise ManifestError(f"{task_id} has unknown eval reference: {', '.join(unknown_evals)}")

    _validate_exact_scalar_references(
        release_gates, requirement_ids, eval_ids, task_ids, "release-1-release-gates"
    )
    return {
        "release": "class-os-r1",
        "requirement_count": len(requirement_ids),
        "included_requirement_count": len(included),
        "required_eval_count": len(eval_ids),
        "task_count": len(task_ids),
    }


def _exact_id_list(value: Any, pattern: re.Pattern[str], context: str) -> list[str]:
    values = _expect_list(value, context)
    if any(not isinstance(item, str) or not pattern.fullmatch(item) for item in values):
        raise ManifestError(f"{context} must contain exact IDs; ranges and expressions are not machine inputs")
    _unique_ids(values, context)
    return values


def _validate_task_source_rows(
    source_path: Path, task_entries: list[dict[str, Any]]
) -> dict[str, str]:
    rows: dict[str, tuple[int, int, str]] = {}
    for line_number, line in enumerate(_read_text(source_path).splitlines(), start=1):
        match = TASK_SOURCE_ROW_RE.match(line)
        if not match:
            continue
        task_id, effort = match.group(1), int(match.group(2))
        if task_id in rows:
            raise ManifestError(f"duplicate source task row: {task_id}")
        normalized = unicodedata.normalize("NFC", line.rstrip())
        rows[task_id] = (line_number, effort, hashlib.sha256(normalized.encode("utf-8")).hexdigest())

    entry_ids = {entry["task_id"] for entry in task_entries}
    if set(rows) != entry_ids:
        raise ManifestError(
            f"task source/definition mismatch; missing={sorted(set(rows) - entry_ids)}, "
            f"extra={sorted(entry_ids - set(rows))}"
        )
    hashes: dict[str, str] = {}
    for entry in task_entries:
        task_id = entry["task_id"]
        line_number, effort, actual_hash = rows[task_id]
        if entry["source_line"] != line_number:
            raise ManifestError(f"{task_id} source_line mismatch: expected {line_number}")
        if entry["effort_days"] != effort:
            raise ManifestError(f"{task_id} effort_days mismatch: expected {effort}")
        declared_hash = entry["task_body_sha256"]
        if not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash):
            raise ManifestError(f"{task_id} task_body_sha256 is invalid")
        if declared_hash != actual_hash:
            raise ManifestError(f"{task_id} task body hash mismatch")
        hashes[task_id] = actual_hash
    return hashes


def _validate_acyclic(dependencies: dict[str, tuple[str, ...]]) -> None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            start = visiting.index(task_id)
            raise ManifestError("task dependency cycle: " + " -> ".join(visiting[start:] + [task_id]))
        if task_id in visited:
            return
        visiting.append(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.pop()
        visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)


def _transitive_closure(
    roots: Iterable[str], dependencies: dict[str, tuple[str, ...]], context: str
) -> frozenset[str]:
    result: set[str] = set()
    stack = list(roots)
    unknown = sorted(set(stack) - set(dependencies))
    if unknown:
        raise ManifestError(f"{context} has unknown task roots: {', '.join(unknown)}")
    while stack:
        task_id = stack.pop()
        if task_id in result:
            continue
        result.add(task_id)
        stack.extend(dependencies[task_id])
    return frozenset(result)


def _validate_task_state(
    repo_root: Path,
    definition_path: Path,
    task_ids: set[str],
    dependencies: dict[str, tuple[str, ...]],
    allowed_statuses: set[str],
) -> dict[str, str]:
    state = _load_yaml(repo_root / ".ai/gates/release-1-tasks.yaml")
    _expect_exact_keys(state, TASK_STATE_ROOT_KEYS, "release-1-tasks root")
    _expect_identity(
        state,
        {
            "schema_version": 2,
            "release": "class-os-r1",
            "artifact_role": "mutable-task-run-state",
            "definition_manifest": ".ai/gates/release-1-task-definitions.yaml",
            "signature_policy": ".ai/gates/signed-artifact-policy.yaml",
            "default_status": "planned",
        },
        "release-1-tasks",
    )
    pinned = state.get("definition_sha256")
    if pinned is not None:
        actual = hashlib.sha256(definition_path.read_bytes()).hexdigest()
        if not isinstance(pinned, str) or not SHA256_RE.fullmatch(pinned) or pinned != actual:
            raise ManifestError("pinned task definition digest does not match immutable definitions")

    entries = _expect_list(state.get("tasks"), "task state entries")
    statuses: dict[str, str] = {}
    entries_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_entry in enumerate(entries):
        entry = _expect_mapping(raw_entry, f"task state[{index}]")
        _expect_keys(entry, TASK_STATE_ENTRY_KEYS, f"task state[{index}]")
        missing = sorted(TASK_STATE_ENTRY_KEYS - set(entry))
        if missing:
            raise ManifestError(f"task state[{index}] missing keys: {', '.join(missing)}")
        task_id = entry["task_id"]
        if not isinstance(task_id, str) or not TASK_RE.fullmatch(task_id):
            raise ManifestError(f"task state[{index}] task_id must be an exact task ID")
        if task_id in statuses:
            raise ManifestError(f"duplicate task state: {task_id}")
        status = entry["status"]
        if status not in allowed_statuses:
            raise ManifestError(f"{task_id} has invalid task status: {status!r}")
        statuses[task_id] = status
        entries_by_id[task_id] = entry
    if set(statuses) != task_ids:
        raise ManifestError(
            f"task state coverage mismatch; missing={sorted(task_ids - set(statuses))}, "
            f"extra={sorted(set(statuses) - task_ids)}"
        )

    for task_id, status in statuses.items():
        entry = entries_by_id[task_id]
        if status == "planned" and (entry["target_commit"] is not None or entry["evidence"] is not None):
            raise ManifestError(f"planned task {task_id} must not carry completion evidence")
        if status != "complete":
            continue
        for dependency in dependencies[task_id]:
            if statuses[dependency] != "complete":
                raise ManifestError(f"{task_id} is complete but dependency {dependency} is not complete")
        if not isinstance(entry["target_commit"], str) or not COMMIT_RE.fullmatch(entry["target_commit"]):
            raise ManifestError(f"complete task {task_id} requires an exact target commit")
        if not isinstance(entry["evidence"], dict) or not entry["evidence"]:
            raise ManifestError(f"complete task {task_id} requires signed evidence metadata")
        if state.get("state_transition_artifact") is None:
            raise ManifestError(f"complete task {task_id} requires a verified state transition artifact")
        for field in ("definition_sha256", "definition_bundle_sha256", "target_release_digest", "target_commit"):
            if state.get(field) is None:
                raise ManifestError(f"complete task {task_id} requires bound task state field {field}")
        if entry["target_commit"] != state["target_commit"]:
            raise ManifestError(f"complete task {task_id} target commit does not match task state")
        raise ManifestError(
            f"complete task {task_id} cannot be trusted without a verified evidence adapter"
        )
    return statuses


def _validate_eval_state(
    repo_root: Path,
    definition_path: Path,
    eval_entries: list[dict[str, Any]],
    signed_policy: dict[str, Any],
) -> int:
    state = _load_yaml(repo_root / ".ai/gates/release-1-eval-state.yaml")
    _expect_exact_keys(state, EVAL_STATE_ROOT_KEYS, "release-1-eval-state root")
    _expect_identity(
        state,
        {
            "schema_version": 2,
            "release": "class-os-r1",
            "artifact_role": "mutable-eval-run-state",
            "definition_manifest": ".ai/gates/release-1-evals.yaml",
            "signature_policy": ".ai/gates/signed-artifact-policy.yaml",
            "default_run_status": "not-run",
            "default_evidence": None,
        },
        "release-1-eval-state",
    )
    definition = _load_yaml(definition_path)
    allowed = set(definition["run_state_contract"]["allowed_statuses"])
    spec_by_id = {entry["eval_id"]: entry["spec_status"] for entry in eval_entries}
    overrides = _expect_list(state.get("overrides"), "eval state overrides")
    seen: set[str] = set()
    green_count = 0
    required_evidence = set(signed_policy["evidence_contracts"]["eval_run_required_fields"])
    for index, raw_entry in enumerate(overrides):
        entry = _expect_mapping(raw_entry, f"eval state override[{index}]")
        _expect_keys(entry, EVAL_STATE_ENTRY_KEYS, f"eval state override[{index}]")
        missing = sorted(EVAL_STATE_ENTRY_KEYS - set(entry))
        if missing:
            raise ManifestError(f"eval state override[{index}] missing keys: {', '.join(missing)}")
        eval_id = entry["eval_id"]
        if eval_id not in spec_by_id or eval_id in seen:
            raise ManifestError(f"unknown or duplicate eval state override: {eval_id!r}")
        seen.add(eval_id)
        status = entry["status"]
        if status not in allowed:
            raise ManifestError(f"{eval_id} has invalid run status: {status!r}")
        if status != "implemented-green":
            continue
        if spec_by_id[eval_id] != "executable-spec":
            raise ManifestError(f"catalogued eval {eval_id} cannot be implemented-green")
        evidence = entry["evidence"]
        if not isinstance(evidence, dict) or not required_evidence.issubset(evidence):
            raise ManifestError(f"implemented-green eval {eval_id} lacks signed evidence contract")
        if state.get("state_transition_artifact") is None:
            raise ManifestError(f"implemented-green eval {eval_id} lacks a verified state transition artifact")
        pinned = state.get("definition_sha256")
        actual = hashlib.sha256(definition_path.read_bytes()).hexdigest()
        if not isinstance(pinned, str) or pinned != actual:
            raise ManifestError(f"implemented-green eval {eval_id} has stale definition binding")
        if state.get("target_release_digest") is None or state.get("target_commit") is None:
            raise ManifestError(f"implemented-green eval {eval_id} lacks target binding")
        if evidence.get("target_release_digest") != state["target_release_digest"]:
            raise ManifestError(f"implemented-green eval {eval_id} release binding mismatch")
        if evidence.get("target_commit") != state["target_commit"]:
            raise ManifestError(f"implemented-green eval {eval_id} commit binding mismatch")
        raise ManifestError(
            f"implemented-green eval {eval_id} cannot be trusted without a verified evidence adapter"
        )
    return green_count


def validate_task_graph(repo_root: Path) -> dict[str, Any]:
    """Validate immutable task DAG and keep definition/run state strictly separate."""

    repo_root = Path(repo_root)
    gates = repo_root / ".ai/gates"
    task_definition_path = gates / "release-1-task-definitions.yaml"
    task_manifest = _load_yaml(task_definition_path)
    _expect_exact_keys(task_manifest, TASK_ROOT_KEYS, "release-1-task-definitions root")
    _expect_identity(
        task_manifest,
        {
            "schema_version": 2,
            "release": "class-os-r1",
            "artifact_role": "immutable-task-definition",
            "source": "docs/specs/class-os-v1/release-1-atomic-tasks.md",
            "state_manifest": ".ai/gates/release-1-tasks.yaml",
            "approval_state": ".ai/gates/release-1-definition-state.yaml",
            "signature_policy": ".ai/gates/signed-artifact-policy.yaml",
        },
        "release-1-task-definitions",
    )
    task_entries = [
        _expect_mapping(entry, f"task_definitions[{index}]")
        for index, entry in enumerate(_expect_list(task_manifest.get("task_definitions"), "task_definitions"))
    ]
    for index, entry in enumerate(task_entries):
        _expect_exact_keys(entry, TASK_ENTRY_KEYS, f"task_definitions[{index}]")
        task_id = entry.get("task_id")
        if not isinstance(task_id, str) or not TASK_RE.fullmatch(task_id):
            raise ManifestError(f"task_definitions[{index}] task_id must be an exact task ID")
    task_ids = _unique_ids([entry["task_id"] for entry in task_entries], "task_id")
    requirement_manifest = _load_yaml(gates / "release-1-requirements.yaml")
    requirement_ids = set(requirement_manifest["included"]) | set(requirement_manifest["excluded"])
    eval_definition_path = gates / "release-1-evals.yaml"
    eval_manifest = _load_yaml(eval_definition_path)
    _expect_exact_keys(eval_manifest, EVAL_ROOT_KEYS, "release-1-evals root")
    _expect_identity(
        eval_manifest,
        {
            "schema_version": 2,
            "release": "class-os-r1",
            "artifact_role": "immutable-eval-definition",
            "run_state_manifest": ".ai/gates/release-1-eval-state.yaml",
            "approval_state": ".ai/gates/release-1-definition-state.yaml",
            "signature_policy": ".ai/gates/signed-artifact-policy.yaml",
        },
        "release-1-evals",
    )
    eval_entries = [
        _expect_mapping(entry, f"required_evals[{index}]")
        for index, entry in enumerate(_expect_list(eval_manifest.get("required_evals"), "required_evals"))
    ]
    eval_ids = {entry["eval_id"] for entry in eval_entries}

    dependencies: dict[str, tuple[str, ...]] = {}
    for index, entry in enumerate(task_entries):
        task_id = entry["task_id"]
        deps = _exact_id_list(entry["depends_on"], TASK_RE, f"{task_id}.depends_on")
        requirements = _exact_id_list(
            entry["requirement_ids"], REQUIREMENT_RE, f"{task_id}.requirement_ids"
        )
        evals = _exact_id_list(entry["eval_ids"], EVAL_RE, f"{task_id}.eval_ids")
        rules = _expect_list(entry["rule_ids"], f"{task_id}.rule_ids")
        if any(not isinstance(rule, str) or not re.fullmatch(r"R-[A-Z0-9]+-\d{3}", rule) for rule in rules):
            raise ManifestError(f"{task_id}.rule_ids must contain exact rule IDs")
        _unique_ids(rules, f"{task_id}.rule_ids")
        if set(deps) - task_ids:
            raise ManifestError(f"{task_id} has unknown task dependencies: {sorted(set(deps) - task_ids)}")
        if set(requirements) - requirement_ids:
            raise ManifestError(f"{task_id} has unknown requirements: {sorted(set(requirements) - requirement_ids)}")
        if set(evals) - eval_ids:
            raise ManifestError(f"{task_id} has unknown evals: {sorted(set(evals) - eval_ids)}")
        dependencies[task_id] = tuple(deps)

    _validate_acyclic(dependencies)
    source_path = repo_root / str(task_manifest["source"])
    _validate_task_source_rows(source_path, task_entries)
    allowed_task_statuses = set(task_manifest["policy"]["allowed_state_statuses"])
    statuses = _validate_task_state(
        repo_root, task_definition_path, task_ids, dependencies, allowed_task_statuses
    )
    signed_policy = _load_yaml(gates / "signed-artifact-policy.yaml")
    green_count = _validate_eval_state(
        repo_root, eval_definition_path, eval_entries, signed_policy
    )

    release_gates = _load_yaml(gates / "release-1-release-gates.yaml")
    _expect_exact_keys(release_gates, RELEASE_GATE_ROOT_KEYS, "release-1-release-gates root")
    _expect_identity(
        release_gates,
        {
            "schema_version": 2,
            "release": "class-os-r1",
            "artifact_role": "immutable-release-gate-definition",
            "state_manifest": ".ai/gates/release-1-release-gate-state.yaml",
            "approval_state": ".ai/gates/release-1-definition-state.yaml",
            "signature_policy": ".ai/gates/signed-artifact-policy.yaml",
            "task_definition_manifest": ".ai/gates/release-1-task-definitions.yaml",
            "task_state_manifest": ".ai/gates/release-1-tasks.yaml",
            "eval_definition_manifest": ".ai/gates/release-1-evals.yaml",
            "eval_state_manifest": ".ai/gates/release-1-eval-state.yaml",
        },
        "release-1-release-gates",
    )
    feature_roots = _exact_id_list(
        release_gates["before_feature_task"]["required_task_roots"],
        TASK_RE,
        "before_feature_task.required_task_roots",
    )
    # This diagnostic follows the current immutable definition, not string ordering
    # of lifecycle labels. It never verifies signatures or grants authority.
    selector = release_gates["before_feature_task"]["required_eval_selector"]
    if selector != {
        "include_required_before": ["first-feature-task"], "unknown_required_before": "fail"
    }:
        raise ManifestError("before_feature_task selector differs from the supported definition")
    validate_eval_meta(repo_root)
    feature_evals = sorted(
        entry["eval_id"] for entry in eval_entries
        if entry["required_before"] in selector["include_required_before"]
    )
    feature_catalogued = sorted(
        entry["eval_id"] for entry in eval_entries
        if entry["eval_id"] in feature_evals and entry["spec_status"] == "catalogued"
    )
    feature_closure = _transitive_closure(feature_roots, dependencies, "before feature task")
    candidate_roots = _exact_id_list(
        release_gates["before_release_candidate"]["required_task_roots"],
        TASK_RE,
        "before_release_candidate.required_task_roots",
    )
    pilot_roots = _exact_id_list(
        release_gates["before_pilot_readiness"]["required_task_roots"],
        TASK_RE,
        "before_pilot_readiness.required_task_roots",
    )
    candidate_closure = _transitive_closure(candidate_roots, dependencies, "release candidate")
    pilot_closure = _transitive_closure(pilot_roots, dependencies, "pilot readiness")
    return {
        "release": "class-os-r1",
        "task_count": len(task_ids),
        "source_row_count": len(task_entries),
        "implemented_green_count": green_count,
        "before_feature_task_closure": sorted(feature_closure),
        "before_feature_task_incomplete_tasks": sorted(
            item for item in feature_closure if statuses[item] != "complete"
        ),
        "before_feature_tasks_complete": all(statuses[item] == "complete" for item in feature_closure),
        "before_feature_required_eval_ids": feature_evals,
        "before_feature_catalogued_eval_ids": feature_catalogued,
        "release_candidate_closure_count": len(candidate_closure),
        "pilot_readiness_closure_count": len(pilot_closure),
        "release_candidate_omitted_tasks": sorted(task_ids - candidate_closure),
        "pilot_readiness_omitted_tasks": sorted(task_ids - pilot_closure),
        "release_candidate_tasks_complete": all(statuses[item] == "complete" for item in candidate_closure),
        "pilot_readiness_tasks_complete": all(statuses[item] == "complete" for item in pilot_closure),
        "authorization": False,
    }


def verify_self(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    required_paths = [
        repo_root / ".ai/gates/release-1-requirements.yaml",
        repo_root / ".ai/gates/release-1-evals.yaml",
        repo_root / ".ai/gates/release-1-task-definitions.yaml",
        repo_root / ".ai/gates/release-1-release-gates.yaml",
        repo_root / ".ai/gates/release-1-tasks.yaml",
        repo_root / ".ai/gates/release-1-eval-state.yaml",
        repo_root / "evals/class-os-v1/executable/release-1-p0.md",
    ]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise ManifestError("self check missing required files: " + ", ".join(missing))
    try:
        yaml.load("key: one\nkey: two\n", Loader=UniqueKeyLoader)
    except ManifestError:
        duplicate_guard = True
    else:
        raise ManifestError("duplicate YAML key guard is not active")
    return {
        "release": "class-os-r1",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "pyyaml": yaml.__version__,
        "duplicate_key_guard": duplicate_guard,
        "required_file_count": len(required_paths),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("self", "eval-meta", "gate-graph", "task-graph"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        if args.command == "self":
            result = verify_self(args.repo_root)
        elif args.command == "eval-meta":
            result = validate_eval_meta(args.repo_root)
        elif args.command == "gate-graph":
            result = validate_gate_graph(args.repo_root)
        else:
            result = validate_task_graph(args.repo_root)
    except ManifestError as exc:
        print(f"MANIFEST ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
