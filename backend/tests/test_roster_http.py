from uuid import uuid4

import httpx
import pytest

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_roster_gateway import roster, class_command
from test_identity import identity, PASSWORD


@pytest.mark.db
async def test_http_roster_walk_without_mock_or_agent(roster):
    business, query, _, _, identity, _, _ = roster
    app = create_app(Settings(), identity=identity, business=business, query=query)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        anonymous = await client.get(f"/api/workspaces/{uuid4()}/context")
        assert anonymous.status_code == 401
        challenge = await client.get("/api/identity/context")
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": challenge.json()["csrf_token"]}
        login = await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)
        assert login.status_code == 200
        workspace_id = login.json()["subject"]["workspace_id"]
        headers["x-class-os-csrf"] = login.json()["csrf_token"]
        base = f"/api/workspaces/{workspace_id}"
        assert (await client.get(base + "/context")).json()["data"] is None
        command = class_command()
        preview = await client.post(base + "/commands/preview", json=command.canonical(), headers=headers)
        assert preview.status_code == 200, preview.text
        assert preview.json()["risk"] == "W2"
        assert preview.json()["payload"] == command.canonical()
        proposal_id = preview.json()["proposal_id"]
        commit = {"proposal_id": proposal_id, "idempotency_key": str(uuid4())}
        assert (await client.post(base + "/commands/commit", json=commit, headers=headers)).status_code == 409
        approval = await client.post(base + "/commands/approve", json={"proposal_id": proposal_id,
            "payload_hash": preview.json()["payload_hash"]}, headers=headers)
        assert approval.status_code == 200
        commit["approval"] = approval.json()["approval"]
        created = await client.post(base + "/commands/commit", json=commit, headers=headers)
        assert created.status_code == 200, created.text
        retry = await client.post(base + "/commands/commit", json=commit, headers=headers)
        assert retry.json() == created.json()
        context = await client.get(base + "/context")
        assert context.json()["data"]["class_id"] == str(command.class_id)
        student_id = str(uuid4())
        payload = {"command": "student.create", "student_id": student_id, "class_id": str(command.class_id),
                   "term_id": str(command.term_id), "expected_class_version": 1, "name": "合成学生 HTTP"}
        assert (await client.post(base + "/commands/preview", json=payload)).status_code == 403
        assert (await client.post(base + "/commands/preview", json={**payload, "risk": "W1"}, headers=headers)).status_code == 400
        preview = await client.post(base + "/commands/preview", json=payload, headers=headers)
        created = await client.post(base + "/commands/commit", json={"proposal_id": preview.json()["proposal_id"],
            "idempotency_key": str(uuid4())}, headers=headers)
        assert created.status_code == 200
        path = base + f"/classes/{command.class_id}/terms/{command.term_id}/students"
        result = await client.get(path)
        assert result.json()["data"] == [{"student_id": student_id, "name": payload["name"], "version": 1, "status": "active"}]
        assert result.headers["cache-control"] == "no-store"
        foreign = await client.get(f"/api/workspaces/{uuid4()}/classes/{command.class_id}/terms/{command.term_id}/students")
        assert foreign.status_code == 401 and "合成学生" not in foreign.text
        assert (await client.get("/health/ready")).status_code == 503


@pytest.mark.db
async def test_http_read_audit_outage_does_not_release_data(roster, monkeypatch):
    business, query, store, credentials, identity, _, _ = roster
    app = create_app(Settings(), identity=identity, business=business, query=query)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        client.cookies.set("class_os_session", credentials[0], path="/api")
        client.cookies.set("class_os_client", credentials[1], path="/api")
        client.cookies.set("class_os_csrf", credentials[2], path="/api")
        monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("secret-audit-detail")))
        response = await client.get(f"/api/workspaces/{credentials[3]}/context")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert "secret-audit-detail" not in response.text
        assert "data" not in response.json()
