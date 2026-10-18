"""Original FR-CLS-001 term editing, through private QG/BCG only."""
from uuid import uuid4
from datetime import date, datetime
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import text

from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.application.roster import CommandRejected, AuditUnavailable
from class_os.domain.roster import ChangeTerm, ChangeClass, decode
from class_os.domain.activity import CreateTask
from class_os.domain.risk import Assessment, Command, Risk, evaluate
from class_os.domain.exit_package import CreateExitExport, validate_package


def correction(classroom):
    return ChangeTerm("term.update", classroom.class_id, classroom.term_id, 1, classroom.term_name, "合成更正学期",
                      classroom.start_date, date(2026, 8, 31), classroom.end_date, date(2027, 1, 31))


def test_term_command_is_closed_typed_nonempty_w2_metadata_not_calendar():
    from test_roster_gateway import class_command
    command = correction(class_command())
    assert decode(command.canonical()) == command
    assert len(command.canonical()) == 10
    assert evaluate(Assessment(Command.TERM_UPDATE)).level is Risk.W2
    for changes in ({"command": "term.move"}, {"expected_version": True}, {"expected_version": 2147483647},
                    {"name": " bad"}, {"previous_name": ""}, {"start_date": "2026-09-01"},
                    {"end_date": date(2026, 8, 31)}, {"previous_end_date": date(2026, 9, 1)},
                    {"start_date": datetime(2026, 8, 31)}, {"name": command.previous_name,
                      "start_date": command.previous_start_date, "end_date": command.previous_end_date}):
        with pytest.raises(ValueError):
            replace(command, **changes)
    for changes in ({"auto_switch": True}, {"workspace_id": str(uuid4())}, {"expected_version": False}):
        with pytest.raises(ValueError):
            decode({**command.canonical(), **changes})


@pytest.mark.db
def test_term_correction_changes_only_term_and_keeps_export_references(roster):
    business, query, _, auth, _, owner, _ = roster
    classroom, student, record = seed(roster)
    submit(business, auth, record)
    submit(business, auth, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
                                    "合成学期关联跟进", student_id=student.student_id, source_record_id=record.record_id))
    before = query.exit_summary(*auth)
    command = correction(classroom)
    proposal = business.preview(*auth, command)
    assert proposal.risk == "W2"
    proof = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: business.commit(*auth, proposal.proposal_id, key, proof), range(2)))
    assert receipts[0] == receipts[1] and receipts[0].resource_id == classroom.term_id and receipts[0].version == 2
    metadata = query.term_metadata(*auth, classroom.class_id, classroom.term_id)
    assert metadata.name == command.name and metadata.version == 2
    assert query.context(*auth).term_name == command.name and query.context(*auth).version == 1
    assert query.roster(*auth, classroom.class_id, classroom.term_id)[0].student_id == student.student_id
    after = query.exit_summary(*auth)
    assert after.counts == before.counts and after.core_hash != before.core_hash
    export = CreateExitExport(uuid4(), after.core_hash)
    submit(business, auth, export)
    bundle = query.exit_download(*auth, export.export_id).bundle
    validate_package(bundle)
    assert bundle["core"]["academic_term"][0]["term_id"] == str(classroom.term_id)
    assert bundle["core"]["academic_term"][0]["version"] == 2
    assert bundle["core"]["manual_task"][0]["source_record_id"] == str(record.record_id)
    with owner.transaction(read_only=True) as connection:
        for table, identifier in (("enrollment", student.student_id), ("record_revision", record.record_id)):
            # Fixed test-owned SQL; production repositories never interpolate identifiers.
            statement = "SELECT class_id,term_id FROM class_os.enrollment WHERE student_id=:id" if table == "enrollment" else "SELECT class_id,term_id FROM class_os.record_revision WHERE record_id=:id"
            assert connection.execute(text(statement), {"id": identifier}).one() == (classroom.class_id, classroom.term_id)
        assert connection.execute(text("SELECT version FROM class_os.student WHERE student_id=:id"), {"id": student.student_id}).scalar_one() == 1
        audits = connection.execute(text("SELECT class_id,term_id,resource_id,resource_version FROM class_os.business_audit WHERE receipt_id=:id"),
                                    {"id": receipts[0].receipt_id}).all()
        assert len(audits) == 2 and all(row == (classroom.class_id, classroom.term_id, classroom.term_id, 2) for row in audits)
    with pytest.raises(CommandRejected):
        business.preview(*auth, command)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["class", "term", "version", "name", "start", "end", "archive-before-approve", "archive-before-commit",
                                 "edit-before-approve", "edit-before-commit"])
def test_term_wrong_scope_stale_metadata_or_parent_archive_never_writes(roster, fault):
    business, query, _, auth, _, _, _ = roster
    classroom, _, _ = seed(roster)
    command = correction(classroom)
    changes = {"class": {"class_id": uuid4()}, "term": {"term_id": uuid4()}, "version": {"expected_version": 2},
               "name": {"previous_name": "合成错误旧名"}, "start": {"previous_start_date": date(2026, 9, 2)},
               "end": {"previous_end_date": date(2027, 1, 29)}}
    if fault in changes:
        with pytest.raises(CommandRejected):
            business.preview(*auth, replace(command, **changes[fault]))
    else:
        proposal = business.preview(*auth, command)
        proof = business.approve(*auth, proposal.proposal_id, proposal.payload_hash) if fault.endswith("commit") else None
        if fault.startswith("archive"):
            submit(business, auth, ChangeClass("class.archive", classroom.class_id, classroom.term_id, 1, classroom.name))
        else:
            submit(business, auth, replace(command, name="合成另一更正"))
        with pytest.raises(CommandRejected):
            if proof:
                business.commit(*auth, proposal.proposal_id, uuid4(), proof)
            else:
                business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
        if fault.startswith("archive"):
            with pytest.raises(CommandRejected):
                query.term_metadata(*auth, classroom.class_id, classroom.term_id)
        else:
            assert query.term_metadata(*auth, classroom.class_id, classroom.term_id).name == "合成另一更正"


@pytest.mark.db
def test_term_audit_failure_rolls_back_and_original_key_can_succeed(roster, monkeypatch):
    business, query, store, auth, _, _, _ = roster
    classroom, _, _ = seed(roster)
    command = correction(classroom)
    proposal = business.preview(*auth, command)
    proof = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(store, "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            business.commit(*auth, proposal.proposal_id, key, proof)
        with pytest.raises(AuditUnavailable):
            query.term_metadata(*auth, classroom.class_id, classroom.term_id)
    assert query.term_metadata(*auth, classroom.class_id, classroom.term_id).version == 1
    assert query.command_status(*auth, proposal.proposal_id, key).status == "not_committed"
    assert business.commit(*auth, proposal.proposal_id, key, proof).version == 2


@pytest.mark.db
def test_term_grants_do_not_expand_key_identity_delete_or_ddl_authority(roster):
    _, _, _, _, _, owner, _ = roster
    with owner.transaction(read_only=True) as connection:
        for column in ("name", "start_date", "end_date"):
            assert connection.execute(text("SELECT pg_catalog.has_column_privilege('class_os_runtime','class_os.academic_term',:column,'UPDATE')"), {"column": column}).scalar_one()
            assert not connection.execute(text("SELECT pg_catalog.has_column_privilege('class_os_identity','class_os.academic_term',:column,'UPDATE')"), {"column": column}).scalar_one()
        for column in ("term_id", "workspace_id", "created_by", "created_at"):
            assert not connection.execute(text("SELECT pg_catalog.has_column_privilege('class_os_runtime','class_os.academic_term',:column,'UPDATE')"), {"column": column}).scalar_one()
        assert not connection.execute(text("SELECT pg_catalog.has_table_privilege('class_os_runtime','class_os.academic_term','DELETE') OR pg_catalog.has_schema_privilege('class_os_runtime','class_os','CREATE')")).scalar_one()


@pytest.mark.db
async def test_term_http_preview_is_existing_r1_w2_metadata_edit(roster):
    business, query, _, auth, boundary, _, _ = roster
    classroom, _, _ = seed(roster)
    app = create_app(Settings(), identity=boundary, business=business, query=query)
    command = {"command": "term.update", "class_id": str(classroom.class_id), "term_id": str(classroom.term_id),
               "expected_version": 1, "previous_name": classroom.term_name, "name": "合成更正学期",
               "previous_start_date": classroom.start_date.isoformat(), "start_date": "2026-08-31",
               "previous_end_date": classroom.end_date.isoformat(), "end_date": "2027-01-31"}
    base = f"/api/workspaces/{auth[3]}"
    headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": auth[2]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        for name, token in zip(("session", "client", "csrf"), auth[:3]):
            client.cookies.set("class_os_" + name, token, path="/api")
        assert (await client.post(base + "/commands/preview", json=command)).status_code == 403
        assert (await client.post(base + "/commands/preview", json={**command, "auto_switch": True}, headers=headers)).status_code == 400
        assert (await client.get(base + f"/classes/{uuid4()}/terms/{classroom.term_id}/metadata")).status_code == 409
        preview = await client.post(base + "/commands/preview", json=command, headers=headers)
        assert preview.status_code == 200
        assert preview.json()["risk"] == "W2" and preview.json()["payload"] == command
        key = str(uuid4())
        body = {"proposal_id": preview.json()["proposal_id"], "idempotency_key": key}
        assert (await client.post(base + "/commands/commit", json=body, headers=headers)).status_code == 409
        approval = await client.post(base + "/commands/approve", json={"proposal_id": body["proposal_id"],
                                      "payload_hash": preview.json()["payload_hash"]}, headers=headers)
        committed = await client.post(base + "/commands/commit", json={**body, "approval": approval.json()["approval"]}, headers=headers)
        assert committed.status_code == 200
        assert committed.json()["resource_id"] == str(classroom.term_id) and committed.json()["version"] == 2
        metadata = await client.get(base + f"/classes/{classroom.class_id}/terms/{classroom.term_id}/metadata")
        assert metadata.status_code == 200 and metadata.headers["cache-control"] == "no-store"
        assert metadata.json() == {"schema_version": "class-os.term-metadata.v1", "class_id": str(classroom.class_id),
                                   "term_id": str(classroom.term_id), "name": command["name"], "version": 2,
                                   "start_date": command["start_date"], "end_date": command["end_date"]}
