from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.roster import AuditUnavailable, CommandRejected
from class_os.application.identity import IdentityDenied
from class_os.domain.activity import CreateRecord
from class_os.domain.roster import CreateStudent
from test_activity_gateway import submit
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_roster_gateway import roster, create_class
from test_identity import identity


@pytest.mark.db
def test_command_scope_and_owner_audit_projection_are_durable_and_minimal(roster):
    gateway, query, store, credentials, _, owner, clock = roster
    classroom, receipt = create_class(gateway, credentials)
    with owner.transaction(read_only=True) as connection:
        row = connection.execute(text("SELECT class_id,term_id FROM class_os.business_audit WHERE receipt_id=:id"),
                                 {"id": receipt.receipt_id}).one()
        assert tuple(row) == (classroom.class_id, classroom.term_id)
    result = query.audit_log(*credentials, classroom.class_id, classroom.term_id)
    assert result["partial_history"] is True and not result["truncated"]
    committed = next(item for item in result["entries"] if item["action"] == "command.commit")
    assert committed["resource_id"] == receipt.resource_id and committed["resource_version"] == 1
    assert set(committed) == {"event_id", "action", "outcome", "occurred_at", "proposal_id", "payload_hash",
                              "receipt_id", "resource_id", "resource_version"}
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='audit.list' AND outcome='allowed'")).scalar_one() == 1
    with pytest.raises(ProgrammingError) as failure:
        with store.database.transaction(read_only=True) as connection:
            connection.execute(text("SELECT session_digest FROM class_os.business_audit"))
    assert failure.value.orig.sqlstate == "42501"
    student = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, "合成审计学生")
    submit(gateway, credentials, student)
    record = CreateRecord("record.create", uuid4(), classroom.class_id, classroom.term_id, student.student_id,
                          "ordinary_fact", clock[0], "不进入审计摘要的合成原文", "")
    proposal = gateway.preview(*credentials, record)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT purpose FROM class_os.command_proposal WHERE proposal_id=:id"), {"id": proposal.proposal_id}).scalar_one() == "manage-class"
        assert connection.execute(text("SELECT purpose FROM class_os.business_audit WHERE proposal_id=:id"), {"id": proposal.proposal_id}).scalar_one() == "manage-class"
    for _ in range(101):
        query.roster(*credentials, classroom.class_id, classroom.term_id)
    bounded = query.audit_log(*credentials, classroom.class_id, classroom.term_id)
    assert len(bounded["entries"]) == 100 and bounded["truncated"] is True


@pytest.mark.db
def test_audit_query_rejects_scope_and_fails_closed_on_its_own_audit_outage(roster, monkeypatch):
    gateway, query, store, credentials, _, _, _ = roster
    classroom, _ = create_class(gateway, credentials)
    with pytest.raises(IdentityDenied):
        query.audit_log(*credentials[:3], uuid4(), classroom.class_id, classroom.term_id)
    with pytest.raises(CommandRejected):
        query.audit_log(*credentials, uuid4(), classroom.term_id)
    with pytest.raises(CommandRejected):
        query.audit_log(*credentials, classroom.class_id, uuid4())
    def fail(*args):
        raise RuntimeError("Synthetic audit read outage")
    monkeypatch.setattr(store, "audit", fail)
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        query.audit_log(*credentials, classroom.class_id, classroom.term_id)


@pytest.mark.db
@pytest.mark.asyncio
async def test_actual_audit_http_is_authenticated_closed_and_no_fact_or_session_text(roster):
    gateway, query, _, credentials, boundary, _, _ = roster
    classroom, _ = create_class(gateway, credentials)
    app = create_app(Settings(), identity=boundary, business=gateway, query=query)
    path = f"/api/workspaces/{credentials[3]}/classes/{classroom.class_id}/terms/{classroom.term_id}/audit"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
                                 base_url="http://127.0.0.1:8000") as client:
        assert (await client.get(path)).status_code == 401
        for name, value in zip(("class_os_session", "class_os_client", "class_os_csrf"), credentials[:3]):
            client.cookies.set(name, value, path="/api")
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json()["schema_version"] == "class-os.business-audit.v1"
        assert len(response.json()["entries"]) == 3
        assert "session_digest" not in response.text and classroom.name not in response.text
        assert (await client.get(path + "?include_session=true")).status_code == 400
