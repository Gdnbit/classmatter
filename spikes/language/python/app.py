from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "evals/class-os-v1/fixtures/r1/canonical-r1.synthetic.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class AttentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    limit: int = Field(ge=1, le=100)


class AttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: Literal["needs_action", "possible_miss", "waiting_on_others"]
    item_id: UUID
    source_ref: UUID
    summary: str


class AttentionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    as_of: str
    items: list[AttentionItem]


def _project_items(workspace_id: str) -> list[dict[str, str]]:
    if workspace_id != FIXTURE["workspace_a"]["workspace_id"]:
        return []
    task = FIXTURE["tasks"][0]
    missing_record = next(record for record in FIXTURE["records"] if record["kind"] == "homework_missing_fact")
    proposal = FIXTURE["proposals"][0]
    approval = FIXTURE["approval_requests"][0]
    return [
        {
            "bucket": "needs_action",
            "item_id": task["task_id"],
            "source_ref": task["source_ref"],
            "summary": "合成跟进事项",
        },
        {
            "bucket": "possible_miss",
            "item_id": missing_record["record_id"],
            "source_ref": missing_record["student_id"],
            "summary": "合成待核对事实",
        },
        {
            "bucket": "waiting_on_others",
            "item_id": approval["approval_request_id"],
            "source_ref": proposal["proposal_id"],
            "summary": "合成等待确认事项",
        },
    ]


app = FastAPI(title="Class OS language spike", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/attention/list", response_model=AttentionResponse)
def attention_list(request: AttentionRequest) -> AttentionResponse:
    workspace_id = str(request.workspace_id)
    known_workspaces = {FIXTURE["workspace_a"]["workspace_id"], FIXTURE["workspace_b"]["workspace_id"]}
    if workspace_id not in known_workspaces:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND_SAFE"})
    return AttentionResponse(
        workspace_id=request.workspace_id,
        as_of=FIXTURE["meta"]["clock"],
        items=_project_items(workspace_id)[: request.limit],
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8761")), log_level="warning")
