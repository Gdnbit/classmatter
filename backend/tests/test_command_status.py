from datetime import timedelta
from uuid import uuid4

import pytest
import httpx

from class_os.application.identity import IdentityDenied
from class_os.application.roster import AuditUnavailable, CommandRejected
from class_os.domain.roster import CreateStudent
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_identity import identity
from test_roster_gateway import roster, class_command


@pytest.mark.db
def test_status_reuses_actual_receipt_without_reapplying_even_after_proposal_expiry(roster):
    gateway, query, _, credentials, _, _, clock = roster
    proposal = gateway.preview(*credentials, class_command())
    key = uuid4()
    before = query.command_status(*credentials, proposal.proposal_id, key)
    assert before.status == "not_committed" and before.receipt is None
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    receipt = gateway.commit(*credentials, proposal.proposal_id, key, approval)
    clock[0] += timedelta(minutes=11)
    status = query.command_status(*credentials, proposal.proposal_id, key)
    assert status.status == "committed" and status.receipt == receipt and status.payload_hash == proposal.payload_hash
    assert query.command_status(*credentials, proposal.proposal_id, uuid4()).status == "unavailable"
    assert gateway.commit(*credentials, proposal.proposal_id, key, approval) == receipt


@pytest.mark.db
def test_status_rejects_scope_or_mismatched_key_and_its_own_audit_outage(roster, monkeypatch):
    gateway, query, store, credentials, _, _, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    key = uuid4()
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    gateway.commit(*credentials, proposal.proposal_id, key, approval)
    second = gateway.preview(*credentials, CreateStudent(uuid4(), proposal.command.class_id, proposal.command.term_id, 1, "合成状态学生"))
    with pytest.raises(CommandRejected):
        query.command_status(*credentials, second.proposal_id, key)
    gateway.reject(*credentials, second.proposal_id)
    assert query.command_status(*credentials, second.proposal_id, uuid4()).status == "unavailable"
    with pytest.raises(IdentityDenied):
        query.command_status(*credentials[:3], uuid4(), proposal.proposal_id, key)
    with pytest.raises(CommandRejected):
        query.command_status(*credentials, uuid4(), key)
    def fail(*args):
        raise RuntimeError("Synthetic status audit outage")
    monkeypatch.setattr(store, "audit", fail)
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        query.command_status(*credentials, proposal.proposal_id, key)


@pytest.mark.db
@pytest.mark.asyncio
async def test_actual_status_http_is_private_and_returns_only_bound_receipt_metadata(roster):
    gateway, query, _, credentials, boundary, _, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    key = uuid4()
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    receipt = gateway.commit(*credentials, proposal.proposal_id, key, approval)
    app = create_app(Settings(), identity=boundary, business=gateway, query=query)
    path = f"/api/workspaces/{credentials[3]}/commands/{proposal.proposal_id}/receipts/{key}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
                                 base_url="http://127.0.0.1:8000") as client:
        assert (await client.get(path)).status_code == 401
        for name, value in zip(("class_os_session", "class_os_client", "class_os_csrf"), credentials[:3]):
            client.cookies.set(name, value, path="/api")
        response = await client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"schema_version", "proposal_id", "payload_hash", "status", "receipt"}
        assert body["status"] == "committed" and body["receipt"]["receipt_id"] == str(receipt.receipt_id)
        assert "approval" not in response.text and proposal.command.name not in response.text
