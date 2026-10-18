"""Wire DTOs from a fixed source-owned registry, never production DDL.

Hash/reference/semantic validation remains in domain.exit_package.
"""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, create_model

from class_os.domain.exit_package import AUDIT_COLUMNS, CORE_COLUMNS
from .contracts import WireModel


def row_model(name, columns, *, nullable=()):
    definitions = {}
    for key in columns:
        if key.endswith("_id") or key.endswith("_by"):
            kind = UUID
        elif key.endswith("_at") or key in ("valid_from", "valid_to"):
            kind = datetime
        elif key in ("start_date", "end_date"):
            kind = date
        elif key in ("version", "resource_version"):
            kind = int
        else:
            kind = str
        if key in nullable:
            kind = kind | None
        definitions[key] = (kind, Field(...))
    return create_model(name, __base__=WireModel, **definitions)


ExitCore = create_model("ExitCore", __base__=WireModel, **{
    table: (list[row_model(table + "ExitRow", columns,
                          nullable=("valid_to", "due_at", "related_record_id", "source_record_id", "student_id") if table == "manual_task" else ("valid_to", "related_record_id"))], Field(max_length=10000))
    for table, columns in CORE_COLUMNS.items()
})
AuditReference = row_model("ExitAuditReference", AUDIT_COLUMNS,
                          nullable=("proposal_id", "payload_hash", "receipt_id", "resource_id", "resource_version", "class_id", "term_id"))


class LifecycleStatus(WireModel):
    complete: Literal[False]
    missing: list[str]


class ExitPackageResponse(WireModel):
    schema_version: Literal["class-os.synthetic-core-exit.v1"]
    purpose: Literal["synthetic-core-recovery"]
    workspace_id: UUID
    created_at: datetime
    actor_refs: list[UUID] = Field(min_length=1, max_length=1)
    core: ExitCore
    audit_refs: list[AuditReference] = Field(max_length=10000)
    core_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    package_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    nonportable: list[str]
    lifecycle_status: LifecycleStatus
