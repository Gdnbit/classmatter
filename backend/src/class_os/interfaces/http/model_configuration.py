"""Private model controls; durable changes remain typed W2 Business Commands."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException
from pydantic import Field, SecretStr, field_validator
import anyio

from class_os.application.model_configuration import ModelConfiguration, Protocol
from .contracts import WireModel
from .roster import credentials
from .roster import ModelControlBody


class ModelConfigurationBody(WireModel):
    protocol: Protocol
    model: str = Field(strict=True, min_length=1, max_length=128)
    base_url: str = Field(strict=True, min_length=1, max_length=512)


class ModelConfigurationResponse(WireModel):
    schema_version: Literal["class-os.model-configuration.v1"]
    status: Literal["syntax-valid-not-enabled"]
    configuration: ModelConfigurationBody
    persisted: Literal[False]
    enabled: Literal[False]
    network_tested: Literal[False]


class ModelStageBody(ModelConfigurationBody):
    expected_version: int = Field(strict=True, ge=0, lt=2147483647)
    api_key: SecretStr = Field(min_length=1, max_length=2048)


class ModelStaged(WireModel):
    schema_version: Literal["class-os.model-staged.v1"]
    command: ModelControlBody


class ModelStatus(WireModel):
    schema_version: Literal["class-os.model-status.v1"]
    storage_available: bool = Field(strict=True)
    version: int = Field(strict=True, ge=0)
    candidate_id: UUID | None
    configuration: ModelConfigurationBody | None
    key_configured: bool = Field(strict=True)
    network_permitted: bool = Field(strict=True)
    test_passed: bool = Field(strict=True)
    mode: Literal["offline", "configured-api", "stale"]


class ModelTestBody(WireModel):
    candidate_id: UUID
    version: int = Field(strict=True, ge=1)
    request_id: UUID
    confirm_network: Literal[True]

    @field_validator("confirm_network", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if type(value) is not bool or value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class ModelEnableBody(WireModel):
    candidate_id: UUID
    version: int = Field(strict=True, ge=1)
    confirm_network: Literal[True]

    @field_validator("confirm_network", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if type(value) is not bool or value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class ModelDisableBody(WireModel):
    pass


def router(query, controller=None):
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}/agent/configuration")

    @routes.post("/validate", response_model=ModelConfigurationResponse)
    def validate(workspace_id: UUID, request: Request, body: ModelConfigurationBody):
        # Authenticate exact workspace and complete existing QG read audit.
        # Does not release current_context or obtain a business-write handle.
        query.context(*credentials(request, workspace_id, write=True))
        config = ModelConfiguration(body.protocol, body.model, body.base_url)
        return ModelConfigurationResponse(schema_version="class-os.model-configuration.v1", status="syntax-valid-not-enabled",
            persisted=False, enabled=False, network_tested=False, configuration=ModelConfigurationBody(
                protocol=config.protocol, model=config.model, base_url=config.base_url))

    async def available(request, workspace):
        auth = credentials(request, workspace, write=True)
        if controller is None:
            await anyio.to_thread.run_sync(lambda: query.context(*auth))
            raise HTTPException(409)
        return auth

    @routes.get("/status", response_model=ModelStatus)
    async def status(workspace_id: UUID, request: Request):
        auth = credentials(request, workspace_id)
        if controller is not None:
            return ModelStatus(**await controller.status(auth))
        row = await anyio.to_thread.run_sync(lambda: query.model_configuration(auth))
        return ModelStatus(schema_version="class-os.model-status.v1", storage_available=False,
            version=row["version"] if row else 0, candidate_id=row["candidate_id"] if row else None,
            configuration={"protocol": row["protocol"], "model": row["model"], "base_url": row["base_url"]} if row and row["sealed"] else None,
            key_configured=bool(row and row["sealed"]), network_permitted=False, test_passed=False, mode="offline")

    @routes.post("/stage", response_model=ModelStaged)
    async def stage(workspace_id: UUID, request: Request, body: ModelStageBody):
        auth = await available(request, workspace_id)
        config = ModelConfiguration(body.protocol, body.model, body.base_url)
        command = await controller.stage(auth, config, body.api_key.get_secret_value(), body.expected_version)
        return ModelStaged(schema_version="class-os.model-staged.v1", command=ModelControlBody(**command.canonical()))

    @routes.post("/test", response_model=ModelStatus)
    async def test(workspace_id: UUID, request: Request, body: ModelTestBody):
        auth = await available(request, workspace_id)
        await controller.test(auth, body.candidate_id, body.version, body.request_id)
        return ModelStatus(**await controller.status(auth))

    @routes.post("/enable", response_model=ModelStatus)
    async def enable(workspace_id: UUID, request: Request, body: ModelEnableBody):
        auth = await available(request, workspace_id)
        await controller.enable(auth, body.candidate_id, body.version)
        return ModelStatus(**await controller.status(auth))

    @routes.post("/disable", response_model=ModelStatus)
    async def disable(workspace_id: UUID, request: Request, body: ModelDisableBody):
        auth = await available(request, workspace_id)
        await controller.disable(auth)
        return ModelStatus(**await controller.status(auth))
    return routes
