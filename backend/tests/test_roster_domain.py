from datetime import date, datetime, timezone
from dataclasses import replace
from uuid import uuid4

import pytest

from class_os.domain.roster import CreateClass, CreateStudent, UpdateIdentifier, decode
from class_os.application.roster import fingerprint


def test_closed_command_roundtrip_and_hash_ignore_json_key_order():
    command = CreateClass(uuid4(), uuid4(), "合成班", "合成学期", date(2026, 9, 1), date(2027, 1, 1))
    payload = command.canonical()
    assert decode(payload) == command
    assert fingerprint(payload) == fingerprint(dict(reversed(list(payload.items()))))
    assert fingerprint(payload) != fingerprint({**payload, "name": "不同合成班"})
    student = CreateStudent(uuid4(), command.class_id, command.term_id, 1, "合成学生")
    assert decode(student.canonical()) == student
    for body in [{**payload, "risk": "W1"}, {**payload, "guardian": "not permitted"},
                 {**payload, "command": "arbitrary.sql"}, {**payload, "name": ""}]:
        with pytest.raises(ValueError):
            decode(body)


@pytest.mark.parametrize("name", ["", " leading", "trailing ", "x" * 81, "a\nname", "a\u202ename", None])
def test_invalid_names_do_not_enter_payload(name):
    with pytest.raises(ValueError):
        CreateStudent(uuid4(), uuid4(), uuid4(), 1, name)


@pytest.mark.parametrize("version", [0, -1, True, "1"])
def test_version_is_not_coerced(version):
    with pytest.raises(ValueError):
        CreateStudent(uuid4(), uuid4(), uuid4(), version, "合成学生")


def test_term_requires_real_dates_in_order():
    for start, end in [(date(2026, 9, 1), date(2026, 9, 1)),
                       (datetime(2026, 9, 1), date(2027, 1, 1))]:
        with pytest.raises(ValueError):
            CreateClass(uuid4(), uuid4(), "合成班", "合成学期", start, end)


def test_identifier_extension_preserves_legacy_payload_and_rejects_unknown_fields():
    old = UpdateIdentifier("student.update_identifier", uuid4(), uuid4(), uuid4(), uuid4(), 1,
                           "synthetic-source", "school_number", "SYN-1", datetime(2026, 1, 1, tzinfo=timezone.utc))
    payload = old.canonical()
    assert "supersedes_identifier_id" not in payload
    assert decode(payload) == old
    assert decode({**payload, "supersedes_identifier_id": None}).canonical() == payload
    new = replace(old, supersedes_identifier_id=uuid4())
    assert decode(new.canonical()) == new
    with pytest.raises(ValueError):
        decode({**payload, "overwrite_previous": True})
    with pytest.raises(ValueError):
        replace(old, supersedes_identifier_id=old.identifier_id)
