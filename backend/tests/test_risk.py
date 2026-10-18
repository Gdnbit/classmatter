"""Canonical E-RISK-001..005 unit slice; not a complete command authorization."""
from dataclasses import replace
from itertools import product

import pytest

from class_os.domain.risk import Assessment, Command, DataClass, Risk, evaluate


@pytest.mark.parametrize("command", list(Command))
def test_command_static_floors(command):
    decision = evaluate(Assessment(command))
    expected = Risk.W2 if command.value in {
        "class.create", "class.update", "class.archive", "term.update", "student.update_name", "student.update_identifier", "student.deactivate",
        "record.correct", "record.supersede", "exit_export.create", "model_configuration.save", "model_configuration.clear",
    } else Risk.W1
    assert decision.level == expected
    assert decision.policy_version == "r1.3"
    assert decision.admitted
    assert decision.requires_approval == (expected == Risk.W2)
    assert not decision.requires_recent_reauthentication


@pytest.mark.parametrize("kind", ["discipline", "conversation"])
def test_sensitive_record_kind_escalates(kind):
    decision = evaluate(Assessment(Command.RECORD_CREATE, record_kind=kind))
    assert decision.level == Risk.W2
    assert decision.admitted and decision.requires_approval


def test_attachments_d4_bulk_external_and_irreversible_fail_closed_in_r1():
    base = Assessment(Command.RECORD_CREATE)
    for assessment in [replace(base, attachments=True), replace(base, data_class=DataClass.D4),
                       replace(base, affected_count=2), replace(base, external=True), replace(base, irreversible=True)]:
        decision = evaluate(assessment)
        assert not decision.admitted
        assert decision.level >= Risk.W2
        assert decision.reasons
    for assessment in [replace(base, external=True), replace(base, irreversible=True)]:
        assert evaluate(assessment).level == Risk.X
        assert evaluate(assessment).requires_recent_reauthentication


def test_r1_roster_d3_fields_are_rejected_not_hidden_in_approval():
    assert not evaluate(Assessment(Command.STUDENT_CREATE, data_class=DataClass.D3)).admitted
    assert evaluate(Assessment(Command.TASK_CREATE, data_class=DataClass.D3)).requires_approval


def test_unauthenticated_requests_never_become_admitted():
    assert not evaluate(Assessment(Command.STUDENT_CREATE, authenticated=False)).admitted


@pytest.mark.parametrize("changes", [{"command": "student.create"}, {"command": "arbitrary.sql"},
    {"affected_count": 0}, {"affected_count": True}, {"affected_count": 1.0}, {"data_class": "D2"},
    {"attachments": 1}, {"external": "false"}, {"authenticated": None}, {"record_kind": "unknown"}])
def test_unknown_or_ill_typed_input_is_not_silently_defaulted(changes):
    with pytest.raises(ValueError):
        evaluate(replace(Assessment(Command.STUDENT_CREATE), **changes))


def test_record_kind_on_non_record_is_rejected():
    with pytest.raises(ValueError):
        evaluate(Assessment(Command.TASK_CREATE, record_kind="conversation"))


def test_risk_is_monotonic_across_all_runtime_escalations():
    for command, data_class, attachment, bulk, external, irreversible in product(
            Command, DataClass, (False, True), (1, 2), (False, True), (False, True)):
        base = Assessment(command, data_class=data_class)
        escalated = replace(base, attachments=attachment, affected_count=bulk, external=external, irreversible=irreversible)
        assert evaluate(escalated).level >= evaluate(base).level
        if not evaluate(base).admitted:
            assert not evaluate(escalated).admitted


def test_client_risk_cannot_be_supplied_to_domain_assessment():
    with pytest.raises(TypeError):
        Assessment(Command.STUDENT_CREATE, risk="W1")
