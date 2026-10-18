from fastapi.testclient import TestClient

from app import FIXTURE, app


client = TestClient(app)


def test_attention_contract_and_workspace_projection() -> None:
    workspace_id = FIXTURE["workspace_a"]["workspace_id"]
    response = client.post("/v1/attention/list", json={"workspace_id": workspace_id, "limit": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == workspace_id
    assert body["as_of"] == FIXTURE["meta"]["clock"]
    assert [item["bucket"] for item in body["items"]] == [
        "needs_action",
        "possible_miss",
        "waiting_on_others",
    ]
    assert all(set(item) == {"bucket", "item_id", "source_ref", "summary"} for item in body["items"])


def test_unknown_workspace_is_not_found_safe() -> None:
    response = client.post(
        "/v1/attention/list",
        json={"workspace_id": "00000000-0000-0000-0000-000000000000", "limit": 20},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "NOT_FOUND_SAFE"}}


def test_unknown_request_field_is_rejected() -> None:
    workspace_id = FIXTURE["workspace_a"]["workspace_id"]
    response = client.post(
        "/v1/attention/list",
        json={"workspace_id": workspace_id, "limit": 20, "write": True},
    )
    assert response.status_code == 422
