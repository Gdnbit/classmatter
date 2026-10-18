from datetime import datetime, timezone
from uuid import uuid4

import pytest

from class_os.domain.activity import CreateRecord, ReviseRecord, CreateTask, ChangeTask, decode_activity


def event(**changes):
    return CreateRecord(**({"command": "record.create", "record_id": uuid4(), "class_id": uuid4(), "term_id": uuid4(),
                           "student_id": uuid4(), "kind": "ordinary_fact", "occurred_at": datetime.now(timezone.utc),
                           "fact_text": "合成事实", "observation_text": ""} | changes))


def test_closed_activity_roundtrip_and_no_unknown_fields():
    command = event()
    assert decode_activity(command.canonical()) == command
    with pytest.raises(ValueError):
        decode_activity(command.canonical() | {"inference": "a label"})
    with pytest.raises(ValueError):
        decode_activity(command.canonical() | {"command": "schema.mutate"})


@pytest.mark.parametrize("change", [
    {"kind": "AIInference"}, {"kind": "teacher_observation"}, {"occurred_at": datetime(2026, 1, 1)},
    {"fact_text": "", "observation_text": ""}, {"kind": "leave_returned_fact"},
])
def test_event_rejects_inference_ambiguous_time_and_unlinked_leave(change):
    with pytest.raises(ValueError):
        event(**change)


def test_observation_stays_separate_and_task_completion_requires_evidence():
    observation = event(kind="teacher_observation", fact_text="", observation_text="老师的合成观察")
    assert decode_activity(observation.canonical()) == observation
    identifiers = (uuid4(), uuid4(), uuid4())
    with pytest.raises(ValueError):
        ChangeTask("task.complete", *identifiers, 1, "done")
    with pytest.raises(ValueError):
        ChangeTask("task.update", *identifiers, 1, "overdue")
    task = CreateTask("task.create", *identifiers, "合成跟进")
    assert decode_activity(task.canonical()) == task
