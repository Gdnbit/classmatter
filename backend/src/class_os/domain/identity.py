from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Owner:
    owner_id: UUID
    workspace_id: UUID
    password_hash: str = field(repr=False)
    credential_version: int = 1


@dataclass(frozen=True)
class Session:
    token_digest: str = field(repr=False)
    owner_id: UUID
    client_digest: str = field(repr=False)
    csrf_digest: str = field(repr=False)
    credential_version: int
    purpose: str
    expires_at: datetime
    last_seen_at: datetime
    reauthenticated_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class Bootstrap:
    secret_hash: str = field(repr=False)
    expires_at: datetime
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class RecoveryCode:
    code_id: UUID
    owner_id: UUID
    code_hash: str = field(repr=False)
    credential_version: int
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class Subject:
    owner_id: UUID
    workspace_id: UUID
    session_id: str = field(repr=False)
    reauthenticated_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class IdentityResult:
    token: str = field(repr=False)
    csrf: str = field(repr=False)
    subject: Subject
    recovery_codes: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class IdentityOperation:
    """Short-lived request correlation, never authentication or persistent Memory."""
    request_id: UUID
    action: str
    client: str = field(repr=False)
    csrf: str = field(repr=False)
    token: str | None = field(default=None, repr=False)
