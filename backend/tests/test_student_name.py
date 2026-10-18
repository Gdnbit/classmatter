from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.roster import ChangeStudentName, ChangeClass, DeactivateStudent, CreateStudent, decode
from class_os.domain.activity import CreateTask
from class_os.domain.risk import Assessment, Command, DataClass, Risk, evaluate
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings


def test_name_correction_is_closed_non_identity_matching_and_w2():
    command = ChangeStudentName("student.update_name", uuid4(), uuid4(), uuid4(), 1, "合成原姓名", "合成更正姓名")
    assert decode(command.canonical()) == command
    with pytest.raises(ValueError):
        decode({**command.canonical(), "merge": True})
    assert evaluate(Assessment(Command.STUDENT_NAME)).level is Risk.W2
    assert not evaluate(Assessment(Command.STUDENT_NAME, data_class=DataClass.D3)).admitted
    for change in ({"name": command.previous_name}, {"name": ""}, {"name": " bad"},
                   {"name": "bad\u200b"}, {"expected_version": True}, {"previous_name": ""}):
        with pytest.raises(ValueError):
            replace(command, **change)


@pytest.mark.db
def test_same_name_students_stay_separate_and_name_correction_preserves_all_fact_task_links(roster):
    business, query, _, auth, _, owner, _ = roster
    classroom, student, record = seed(roster)
    submit(business, auth, record)
    task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成关联跟进", student_id=student.student_id, source_record_id=record.record_id)
    submit(business, auth, task)
    other = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, query.context(*auth).version, student.name)
    submit(business, auth, other)
    command = ChangeStudentName("student.update_name", student.student_id, classroom.class_id, classroom.term_id, 1, student.name, "合成更正姓名")
    proposal = business.preview(*auth, command)
    assert proposal.risk == "W2"
    key = uuid4()
    with pytest.raises(CommandRejected):
        business.commit(*auth, proposal.proposal_id, key)
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    receipt = business.commit(*auth, proposal.proposal_id, key, approval)
    assert receipt.resource_id == student.student_id and receipt.version == 2
    assert business.commit(*auth, proposal.proposal_id, key, approval) == receipt
    with owner.transaction(read_only=True) as connection:
        rows = dict(connection.execute(text("SELECT student_id,name FROM class_os.student")).all())
        assert rows == {student.student_id: command.name, other.student_id: student.name}
        assert connection.execute(text("SELECT student_id FROM class_os.record_revision WHERE record_id=:id"), {"id": record.record_id}).scalar_one() == student.student_id
        assert connection.execute(text("SELECT student_id,source_record_id FROM class_os.manual_task WHERE task_id=:id"), {"id": task.task_id}).one() == (student.student_id, record.record_id)
        stored = connection.execute(text("SELECT payload FROM class_os.command_proposal WHERE proposal_id=:p"), {"p": proposal.proposal_id}).scalar_one()
        assert stored["previous_name"] == student.name and stored["name"] == command.name
    with pytest.raises(CommandRejected):
        business.preview(*auth, command)


@pytest.mark.db
def test_name_approval_cannot_outlive_target_version_and_audit_failure_is_atomic(roster, monkeypatch):
    business, query, store, auth, _, owner, _ = roster
    classroom, student, _ = seed(roster)
    command = ChangeStudentName("student.update_name", student.student_id, classroom.class_id, classroom.term_id, 1, student.name, "合成更正一")
    proposal = business.preview(*auth, command)
    stale = business.preview(*auth, replace(command, name="合成更正二"))
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    stale_approval = business.approve(*auth, stale.proposal_id, stale.payload_hash)
    original_audit = store.audit
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    key = uuid4()
    with pytest.raises(RuntimeError, match="audit unavailable"):
        business.commit(*auth, proposal.proposal_id, key, approval)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT name,version FROM class_os.student WHERE student_id=:s"), {"s": student.student_id}).one() == (student.name, 1)
        assert connection.execute(text("SELECT count(*) FROM class_os.command_receipt WHERE proposal_id=:p"), {"p": proposal.proposal_id}).scalar_one() == 0
        assert connection.execute(text("SELECT consumed_at FROM class_os.approval_receipt WHERE proposal_id=:p"), {"p": proposal.proposal_id}).scalar_one() is None
    monkeypatch.setattr(store, "audit", original_audit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: business.commit(*auth, proposal.proposal_id, key, approval), range(2)))
    assert results[0] == results[1]
    with pytest.raises(CommandRejected):
        business.commit(*auth, stale.proposal_id, uuid4(), stale_approval)
    assert query.roster(*auth, classroom.class_id, classroom.term_id)[0].name == command.name


@pytest.mark.db
@pytest.mark.parametrize("invalid_scope", ["student", "class", "term", "old-name", "inactive", "archived"])
def test_name_correction_rejects_wrong_scope_or_inactive_resources(roster, invalid_scope):
    business, query, _, auth, _, _, clock = roster
    classroom, student, _ = seed(roster)
    command = ChangeStudentName("student.update_name", student.student_id, classroom.class_id, classroom.term_id, 1, student.name, "合成更正")
    if invalid_scope in ("student", "class", "term"):
        command = replace(command, **{invalid_scope + "_id": uuid4()})
    elif invalid_scope == "old-name":
        command = replace(command, previous_name="不是当前姓名")
    elif invalid_scope == "inactive":
        submit(business, auth, DeactivateStudent("student.deactivate", student.student_id, classroom.class_id, classroom.term_id, 1))
        command = replace(command, expected_version=2)
    else:
        submit(business, auth, ChangeClass("class.archive", classroom.class_id, classroom.term_id, query.context(*auth).version, classroom.name))
    with pytest.raises(CommandRejected):
        business.preview(*auth, command)


@pytest.mark.db
async def test_name_http_closed_payload_origin_approval_and_shared_query(roster):
    business, query, _, auth, boundary, _, _ = roster
    classroom, student, _ = seed(roster)
    app = create_app(Settings(), identity=boundary, business=business, query=query)
    command = ChangeStudentName("student.update_name", student.student_id, classroom.class_id, classroom.term_id, 1, student.name, "合成HTTP更正")
    base = f"/api/workspaces/{auth[3]}"
    headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": auth[2]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        for name, token in zip(("session", "client", "csrf"), auth[:3]):
            client.cookies.set("class_os_" + name, token, path="/api")
        assert (await client.post(base + "/commands/preview", json=command.canonical())).status_code == 403
        assert (await client.post(base + "/commands/preview", json={**command.canonical(), "merge": True}, headers=headers)).status_code == 400
        preview = await client.post(base + "/commands/preview", json=command.canonical(), headers=headers)
        assert preview.status_code == 200 and preview.json()["risk"] == "W2"
        assert preview.json()["payload"] == command.canonical()
        body = {"proposal_id": preview.json()["proposal_id"], "idempotency_key": str(uuid4())}
        assert (await client.post(base + "/commands/commit", json=body, headers=headers)).status_code == 409
        approval = await client.post(base + "/commands/approve", json={"proposal_id": body["proposal_id"], "payload_hash": preview.json()["payload_hash"]}, headers=headers)
        receipt = await client.post(base + "/commands/commit", json={**body, "approval": approval.json()["approval"]}, headers=headers)
        assert receipt.status_code == 200 and receipt.json()["resource_id"] == str(student.student_id)
        response = await client.get(base + f"/classes/{classroom.class_id}/terms/{classroom.term_id}/students")
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["data"][0]["name"] == command.name
        assert response.json()["data"][0]["student_id"] == str(student.student_id)


@pytest.mark.db
def test_name_grant_does_not_expand_identity_delete_key_or_ddl_authority(roster):
    _, _, _, _, _, owner, _ = roster
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT has_column_privilege('class_os_runtime','class_os.student','name','UPDATE')")).scalar_one()
        for role, column in (("class_os_identity", "name"), ("class_os_runtime", "student_id"), ("class_os_runtime", "workspace_id")):
            assert not connection.execute(text("SELECT has_column_privilege(:role,'class_os.student',:column,'UPDATE')"), {"role": role, "column": column}).scalar_one()
        assert not connection.execute(text("SELECT has_table_privilege('class_os_runtime','class_os.student','DELETE') OR has_schema_privilege('class_os_runtime','class_os','CREATE')")).scalar_one()
