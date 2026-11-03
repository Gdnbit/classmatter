"""Fixed native D2 protocol; not another UI or request-selected permission mode."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field

from .contracts import WireModel
from .durable_views import DurableAuditEntry, AuditResponse as D1AuditResponse
from .roster import credentials


class WorkbenchAuditEntry(DurableAuditEntry):
    action: DurableAuditEntry.model_fields['action'].annotation | Literal['document.list', 'document.read', 'document.history']


class WorkbenchAuditResponse(D1AuditResponse):
    schema_version: Literal['classmatter.business-audit.v2'] = 'classmatter.business-audit.v2'
    entries: list[WorkbenchAuditEntry] = Field(max_length=100)


class WorkbenchCapabilities(WireModel):
    schema_version: Literal['classmatter.workbench-capabilities.v1'] = 'classmatter.workbench-capabilities.v1'
    profile: Literal['workbench-d2']
    data_mode: Literal['synthetic-only']
    history_protocol: Literal['classmatter.conversation-history.v2']
    document_protocol: Literal['classmatter.document.v1']
    complete_exit: Literal[False]


def router(query):
    from class_os.application.workbench import WorkbenchQueryGateway
    if type(query) is not WorkbenchQueryGateway:
        raise ValueError('Exact workbench query required')
    routes = APIRouter(prefix='/api/workspaces/{workspace_id}/workbench-d2')

    @routes.get('/capabilities', response_model=WorkbenchCapabilities)
    def capabilities(workspace_id: UUID, request: Request):
        return query.workbench_capabilities(*credentials(request, workspace_id))

    return routes


def create_workbench_app(settings, *, worker, query, sdk, readiness=None, model_controller=None):
    from .durable_conversation import create_durable_app
    return create_durable_app(settings, worker=worker, query=query, sdk=sdk, readiness=readiness,
                              model_controller=model_controller, _workbench=True)
