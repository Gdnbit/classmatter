from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

from class_os.application.roster import fingerprint
from class_os.domain.activity import CreateRecord, CreateTask, ChangeTask
from class_os.domain.roster import CreateStudent, UpdateIdentifier
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_roster_gateway import roster, create_class
from test_identity import identity
from test_activity_gateway import submit


@pytest.mark.db
@pytest.mark.asyncio
async def test_actual_preview_payload_is_exactly_the_canonical_hash_input(roster):
    business, query, _, credentials, boundary, _, clock = roster
    classroom, _ = create_class(business, credentials)
    student = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, "合成完整性学生")
    submit(business, credentials, student)
    task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成待修改任务")
    submit(business, credentials, task)
    commands = [
        CreateRecord("record.create", uuid4(), classroom.class_id, classroom.term_id, student.student_id,
                     "ordinary_fact", clock[0], "合成时间字段", ""),
        UpdateIdentifier("student.update_identifier", uuid4(), student.student_id, classroom.class_id, classroom.term_id,
                         1, "synthetic-school", "school_number", "SYN-HASH", clock[0]),
        ChangeTask("task.update", task.task_id, task.class_id, task.term_id, 1, "waiting"),
        ChangeTask("task.update", task.task_id, task.class_id, task.term_id, 1, "not-started", title="合成新标题",
                   change_due_date=True, due_at=clock[0] + timedelta(days=1)),
    ]
    app = create_app(Settings(), identity=boundary, business=business, query=query)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
                                 base_url="http://127.0.0.1:8000") as client:
        for name, secret in zip(("class_os_session", "class_os_client", "class_os_csrf"), credentials[:3]):
            client.cookies.set(name, secret, path="/api")
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": credentials[2]}
        for command in commands:
            response = await client.post(f"/api/workspaces/{credentials[3]}/commands/preview", json=command.canonical(), headers=headers)
            assert response.status_code == 200
            body = response.json()
            assert body["schema_version"] == "class-os.roster.v1"
            assert body["payload"] == command.canonical()
            assert fingerprint(body["payload"]) == body["payload_hash"]
