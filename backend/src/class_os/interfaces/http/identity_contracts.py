"""Closed identity wire shapes, separate from cookie capabilities and facts."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator

from .contracts import WireModel


TransportSecret = Annotated[str, Field(strict=True, min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
COOKIE_SECRET = TypeAdapter(TransportSecret)
RecoveryCodeWire = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[A-Za-z0-9_-]{32}$")]


class IdentityChallenge(WireModel):
    schema_version: Literal["class-os.identity.v1"]
    csrf_token: TransportSecret


class IdentitySubject(WireModel):
    owner_id: UUID
    workspace_id: UUID


class IdentitySession(IdentityChallenge):
    subject: IdentitySubject


class IdentityKitSession(IdentitySession):
    recovery_codes: list[RecoveryCodeWire] = Field(min_length=5, max_length=5, strict=True, json_schema_extra={"uniqueItems": True})

    @field_validator("recovery_codes")
    @classmethod
    def unique_selectors(cls, values):
        if len({value.split(".", 1)[0] for value in values}) != 5:
            raise ValueError("Duplicate recovery selector")
        return values


class IdentitySignedOut(WireModel):
    schema_version: Literal["class-os.identity.v1"]
    status: Literal["signed_out", "signed_out_all"]


class IdentityLogoutBody(WireModel):
    request_id: UUID | None = None


class IdentityLogoutReceipt(WireModel):
    schema_version: Literal["class-os.identity-logout-receipt.v1"]
    request_id: UUID
    action: Literal["logout"]
    status: Literal["committed", "not_committed"]


IdentityAction = Literal["bootstrap", "login", "reauthenticate", "logout_all", "recovery_reissue", "recovery_exchange", "recovery_complete"]


class IdentityOperationReceipt(WireModel):
    schema_version: Literal["class-os.identity-operation-receipt.v1"]
    request_id: UUID
    action: IdentityAction
    status: Literal["committed"]
    result_replayable: Literal[False]
