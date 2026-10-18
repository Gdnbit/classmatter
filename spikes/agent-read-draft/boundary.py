from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from class_os_contracts import (
    DraftBuilderPort,
    QueryGatewayPort,
    RouteMode,
    RuntimeRequest,
    ToolDescriptor,
    ToolRisk,
)


CATALOG: dict[str, ToolDescriptor] = {
    "attention.list": ToolDescriptor(
        "attention.list", ToolRisk.READ_ONLY, "attention", "读取当前工作区注意力列表"
    ),
    "task.draft": ToolDescriptor(
        "task.draft", ToolRisk.DRAFT_ONLY, "tasks", "创建可编辑但未提交的任务草稿"
    ),
    "student.update": ToolDescriptor(
        "student.update", ToolRisk.MUTATING_REVERSIBLE, "roster", "修改正式学生信息"
    ),
    "system.fetch_url": ToolDescriptor(
        "system.fetch_url", ToolRisk.EXTERNAL_SIDE_EFFECT, "system", "访问任意 URL"
    ),
    "system.sql": ToolDescriptor(
        "system.sql", ToolRisk.MUTATING_HIGH_IMPACT, "system", "执行 SQL"
    ),
}


class BoundaryViolation(RuntimeError):
    pass


class CapabilityFilter:
    _route_risks = {
        RouteMode.ANSWER_ONLY: frozenset(),
        RouteMode.CLARIFY: frozenset(),
        RouteMode.READ: frozenset({ToolRisk.READ_ONLY}),
        RouteMode.DRAFT_WRITE: frozenset({ToolRisk.READ_ONLY, ToolRisk.DRAFT_ONLY}),
    }

    def visible_tools(self, request: RuntimeRequest) -> tuple[ToolDescriptor, ...]:
        allowed_risks = self._route_risks[request.route_mode]
        visible: list[ToolDescriptor] = []
        for name in sorted(request.requested_tools):
            descriptor = CATALOG.get(name)
            if descriptor is None:
                raise BoundaryViolation(f"unknown tool: {name}")
            if descriptor.risk not in allowed_risks:
                raise BoundaryViolation(f"tool is not visible in R1: {name}")
            visible.append(descriptor)
        return tuple(visible)


@dataclass(slots=True)
class SyntheticQueryGateway(QueryGatewayPort):
    workspaces: dict[str, dict[str, Any]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def attention_list(self, workspace_id: str) -> dict[str, Any]:
        self.calls.append(("attention.list", workspace_id))
        if workspace_id not in self.workspaces:
            raise BoundaryViolation("workspace not found")
        raw = deepcopy(self.workspaces[workspace_id])
        return {
            "as_of": raw["as_of"],
            "items": [
                {
                    "id": item["id"],
                    "bucket": item["bucket"],
                    "title": item["title"],
                    "due_at": item.get("due_at"),
                    "source_ref": item["source_ref"],
                }
                for item in raw["items"]
            ],
        }


@dataclass(slots=True)
class EphemeralDraftBuilder(DraftBuilderPort):
    drafts: list[dict[str, Any]] = field(default_factory=list)
    committed_business_writes: int = 0

    async def build_task_draft(self, workspace_id: str, title: str) -> dict[str, Any]:
        draft = {
            "kind": "task-draft",
            "workspace_id": workspace_id,
            "title": title.strip(),
            "status": "draft",
            "committed": False,
        }
        self.drafts.append(deepcopy(draft))
        return draft


@dataclass(slots=True)
class ToolGateway:
    query_gateway: QueryGatewayPort
    draft_builder: DraftBuilderPort
    calls: list[str] = field(default_factory=list)

    async def execute(self, descriptor: ToolDescriptor, request: RuntimeRequest, **kwargs: Any) -> dict[str, Any]:
        if descriptor.risk not in {ToolRisk.READ_ONLY, ToolRisk.DRAFT_ONLY}:
            raise BoundaryViolation("mutating tools cannot execute through the Agent gateway")
        self.calls.append(descriptor.name)
        if descriptor.name == "attention.list":
            return await self.query_gateway.attention_list(request.workspace_id)
        if descriptor.name == "task.draft":
            title = kwargs.get("title")
            if not isinstance(title, str) or not title.strip():
                raise BoundaryViolation("draft title is required")
            return await self.draft_builder.build_task_draft(request.workspace_id, title)
        raise BoundaryViolation(f"unimplemented allowed tool: {descriptor.name}")
