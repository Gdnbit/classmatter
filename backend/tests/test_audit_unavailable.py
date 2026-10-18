"""Real QG/BCG fault injection, not a formal SecurityTarget adapter."""
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from class_os.application.agent import AgentRequest, Mode
from class_os.application.roster import AuditUnavailable
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_activity_gateway import seed, submit
from test_roster_gateway import roster, class_command
from test_identity import identity


@pytest.mark.db
@pytest.mark.parametrize("surface", ("context", "roster", "timeline", "audit", "exit"))
async def test_business_audit_outage_is_static_503_without_projection(roster, monkeypatch, caplog, surface):
    business, query, store, credentials, boundary, _, _ = roster
    classroom, student, record = seed(roster)
    submit(business, credentials, record)
    paths = {
        "context": "/context", "exit": "/exit/summary",
        "roster": f"/classes/{classroom.class_id}/terms/{classroom.term_id}/students",
        "timeline": f"/classes/{classroom.class_id}/terms/{classroom.term_id}/students/{student.student_id}/timeline",
        "audit": f"/classes/{classroom.class_id}/terms/{classroom.term_id}/audit",
    }
    def outage(*args):
        raise RuntimeError("synthetic-private-audit-canary")
    monkeypatch.setattr(store, "audit", outage)
    app = create_app(Settings(), identity=boundary, business=business, query=query)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345),
                                                            raise_app_exceptions=True),
                                 base_url="http://127.0.0.1:8000") as client:
        for name, value in zip(("class_os_session", "class_os_client", "class_os_csrf"), credentials[:3]):
            client.cookies.set(name, value, path="/api")
        response = await client.get(f"/api/workspaces/{credentials[3]}" + paths[surface])
    assert response.status_code == 503
    assert response.json() == {"schema_version": "class-os.error.v1", "request_id": response.headers["x-request-id"],
                               "error": {"code": "AUDIT_UNAVAILABLE", "message": "Request rejected."}}
    assert response.headers["cache-control"] == "no-store"
    assert "synthetic-private-audit-canary" not in response.text + caplog.text
    assert student.name not in response.text + caplog.text and record.fact_text not in response.text + caplog.text
    signals = [item for item in caplog.records if item.name == "class_os.security"]
    assert len(signals) == 1 and signals[0].exc_info is None
    assert signals[0].getMessage() == "audit_unavailable kind=audit-unavailable"


@pytest.mark.db
@pytest.mark.parametrize("receipt", (None, "synthetic-fake-receipt", 1))
def test_non_uuid_business_audit_receipt_cannot_release_any_projection(roster, monkeypatch, receipt):
    _, query, store, credentials, _, _, _ = roster
    seed(roster)
    monkeypatch.setattr(store, "audit", lambda *args: receipt)
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        query.context(*credentials)


@pytest.mark.db
def test_business_audit_outage_rolls_back_commit_and_allows_original_key_recovery(roster, monkeypatch):
    business, _, store, credentials, _, owner, _ = roster
    command = class_command()
    proposal = business.preview(*credentials, command)
    approval = business.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    original = store.audit
    monkeypatch.setattr(store, "audit", lambda *args: None)
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        business.commit(*credentials, proposal.proposal_id, key, approval)
    with owner.transaction(read_only=True) as connection:
        for table in ("school_class", "academic_term", "command_receipt"):
            assert connection.execute(text(f"SELECT count(*) FROM class_os.{table}")).scalar_one() == 0
        assert connection.execute(text("SELECT consumed_at FROM class_os.approval_receipt")).scalar_one() is None
    monkeypatch.setattr(store, "audit", original)
    result = business.commit(*credentials, proposal.proposal_id, key, approval)
    assert result.resource_id == command.class_id
    assert business.commit(*credentials, proposal.proposal_id, key, approval) == result


@pytest.mark.db
async def test_agent_audit_outage_releases_no_answer_draft_or_history(roster, monkeypatch):
    _, query, store, credentials, _, _, _ = roster
    seed(roster)
    calls = []
    def forbidden_model(request):
        calls.append(request)
        pytest.fail("Provider entered before durable run audit")
    runtime = PydanticAgentRuntime(query, model_factory=forbidden_model)
    conversation = runtime.conversation(credentials)
    original = store.audit
    def missing_run_receipt(connection, binding, action, outcome, now, metadata):
        if action.startswith("agent.run."):
            return None
        return original(connection, binding, action, outcome, now, metadata)
    monkeypatch.setattr(store, "audit", missing_run_receipt)
    events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id,
                                                                              "合成查询", Mode.READ))]
    assert events[-1].type == "run.failed"
    assert not any(item.type in ("message.delta", "draft.available", "run.completed") for item in events)
    assert conversation.history == [] and runtime.active == 0
    assert calls == []
