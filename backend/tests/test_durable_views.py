"""Author-aware D1 transport uses actual QG/BCG/ISB, never mock records."""
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from class_os.domain.activity import CreateRecord, CreateTask
from class_os.interfaces.http.durable_views import DurableAuditEntry, DomainAttribution
from test_durable_conversation_http import setup, client
from test_conversation_control import control, storage, roster, identity


@pytest.mark.db
async def test_d1_views_keep_fact_task_author_and_complete_history_audit_action(control):
    value = setup(control)
    record = CreateRecord("record.create", uuid4(), value.ids["class"], value.ids["term"],
        value.ids["student"], "ordinary_fact", control[7][0], "synthetic current fact", "")
    task = CreateTask("task.create", uuid4(), value.ids["class"], value.ids["term"],
        "synthetic sourced task", None, value.ids["student"], record.record_id)
    for command in (record, task):
        proposal = value.worker.preview(*value.auth, command)
        assert proposal.risk == "W1"
        value.worker.commit(*value.auth, proposal.proposal_id, uuid4())
    async with client(value) as api:
        capability = await api.get(f"/api/workspaces/{value.auth[3]}/conversation-d1/capabilities")
        assert capability.status_code == 200, capability.text
        assert capability.json()["history_protocol"] == "classmatter.conversation-history.v2"
        assert (await api.get(value.thread_path + "/history")).status_code == 200
        for path in (value.base + "/activity", value.base + f"/students/{value.ids['student']}/timeline"):
            response = await api.get(path)
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["schema_version"] == "classmatter.activity.v1"
            assert len(data["data"]["records"]) == len(data["data"]["tasks"]) == 1
            assert data["data"]["tasks"][0]["source_record_id"] == str(record.record_id)
            for row in data["data"]["records"] + data["data"]["tasks"]:
                assert row["attribution"]["origin"] == "local-owner"
                assert row["attribution"]["created_by"] == str(value.ids["owner"])
                assert row["attribution"]["content_authority"] == "domain-data"
        audit = await api.get(value.base + "/audit")
        assert audit.status_code == 200, audit.text
        assert audit.json()["schema_version"] == "classmatter.business-audit.v1"
        assert any(row["action"] == "conversation.history" for row in audit.json()["entries"])
        assert (await api.get(value.base.replace(str(value.auth[3]), str(uuid4())) + "/activity")).status_code in (401, 409)
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.started'")).scalar_one() == 0


@pytest.mark.db
async def test_d1_capabilities_are_authenticated_read_not_a_request_profile_selector(control):
    value = setup(control)
    path = f"/api/workspaces/{value.auth[3]}/conversation-d1/capabilities"
    async with client(value) as api:
        assert (await api.post(path, json={"profile": "conversation-d1"}, headers=value.headers)).status_code == 405
        assert (await api.get(path + "?profile=r1")).status_code == 400
        assert (await api.get(path, headers={"origin": "https://untrusted.invalid"})).status_code == 403
        api.cookies.clear()
        assert (await api.get(path)).status_code == 401


def test_d1_audit_and_domain_attribution_do_not_become_open_json():
    from class_os.interfaces.http.roster import AuditEntry
    assert "conversation.history" not in AuditEntry.model_fields["action"].annotation.__args__
    base = {"event_id": str(uuid4()), "action": "conversation.history", "outcome": "allowed",
        "occurred_at": "2026-10-24T00:00:00Z", "proposal_id": None, "payload_hash": None,
        "receipt_id": None, "resource_id": None, "resource_version": None}
    assert DurableAuditEntry.model_validate(base).action == "conversation.history"
    for invalid in ({**base, "action": "sql.execute"}, {**base, "session_digest": "not-public"}):
        with pytest.raises(ValidationError):
            DurableAuditEntry.model_validate(invalid)
    with pytest.raises(ValidationError):
        DomainAttribution(origin="local-owner", created_by=None, last_modified_by=None,
            source_workspace_id=None, source_owner_id=None, source_version=None, content_authority="assistant-unverified")


@pytest.mark.db
def test_d1_factory_binds_only_matching_original_model_controller_and_stays_offline(control):
    from class_os.infrastructure.model_control import ModelController
    from class_os.infrastructure.model_secrets import ModelSecrets
    from class_os.interfaces.http.durable_conversation import create_durable_app
    from class_os.interfaces.http.settings import Settings
    from test_model_secrets import fixture_codec
    value = setup(control)
    with pytest.raises(ValueError):
        create_durable_app(Settings(), worker=value.worker, query=value.query, sdk=value.sdk, model_controller=object())
    missing = ModelController(value.query, None, value.sdk)
    with pytest.raises(ValueError):
        create_durable_app(Settings(), worker=value.worker, query=value.query, sdk=value.sdk, model_controller=missing)
    vault = ModelSecrets(fixture_codec)
    value.store.model_secrets = vault  # Explicit trusted synthetic fixture composition only.
    controller = ModelController(value.query, vault, value.sdk)
    app = create_durable_app(Settings(), worker=value.worker, query=value.query, sdk=value.sdk, model_controller=controller)
    assert app is not None and value.sdk.model_context.__self__ is controller
    assert value.sdk.provider_state(value.auth) == "synthetic-function-model"
    assert not controller._enabled and not controller._proofs
