from datetime import datetime, timezone
from uuid import uuid4

import pytest

from class_os.domain.query_snapshot import WorkSnapshot


def test_projection_without_actual_receipt_cannot_be_tool_data():
    value = WorkSnapshot(uuid4(), uuid4(), 1, datetime.now(timezone.utc), 1, 1, 0, "a" * 64)
    with pytest.raises(ValueError, match="receipt"):
        value.tool_payload()


@pytest.mark.parametrize("counts", [(-1, 0, 0), (0, 1, 0), (True, 0, 0)])
def test_projection_is_not_an_arbitrary_score_or_inference(counts):
    with pytest.raises(ValueError):
        WorkSnapshot(uuid4(), uuid4(), 1, datetime.now(timezone.utc), *counts, "a" * 64)


@pytest.mark.parametrize("student,version", [(uuid4(), None), (None, 1), ("name", 1), (uuid4(), True), (uuid4(), 0)])
def test_student_scope_must_be_uuid_and_actual_coherent_version(student, version):
    with pytest.raises(ValueError):
        WorkSnapshot(uuid4(), uuid4(), 1, datetime.now(timezone.utc), 0, 0, 0, "a" * 64,
                     student_id=student, student_version=version)
