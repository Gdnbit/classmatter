"""Health metadata only: no Domain Fact or synthetic business repository."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiveResponse(WireModel):
    schema_version: Literal["class-os.health.v1"] = "class-os.health.v1"
    service: Literal["class-os-api"] = "class-os-api"
    mode: Literal["synthetic-development"] = "synthetic-development"
    status: Literal["alive"] = "alive"


class Components(WireModel):
    database: Literal["not_configured", "connected", "unverified"] = "not_configured"
    identity: Literal["not_configured", "connected", "unverified"] = "not_configured"
    business_gateways: Literal["not_configured", "connected", "unverified"] = "not_configured"


class ReadyResponse(WireModel):
    schema_version: Literal["class-os.health.v1"] = "class-os.health.v1"
    service: Literal["class-os-api"] = "class-os-api"
    mode: Literal["synthetic-development"] = "synthetic-development"
    status: Literal["not_ready", "ready"] = "not_ready"
    components: Components = Components()


class ErrorDetail(WireModel):
    code: Literal["local_boundary_rejected", "invalid_request", "not_found", "method_not_allowed", "internal_error", "identity_rejected", "business_rejected", "identity_already_committed", "AUDIT_UNAVAILABLE"]
    message: Literal["Request rejected."] = "Request rejected."


class ErrorResponse(WireModel):
    schema_version: Literal["class-os.error.v1"] = "class-os.error.v1"
    request_id: UUID
    error: ErrorDetail
