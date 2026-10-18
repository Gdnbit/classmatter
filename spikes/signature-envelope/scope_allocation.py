"""Synthetic PostgreSQL proof for the sole pre-admission BCG command.

No API, Agent, worker or request may call this adapter directly in production.
The caller must supply a trusted, freshly verified setup and registry snapshot.
This module never creates a business Class, Term, Student or other aggregate.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import psycopg

from signature_envelope import (
    AdmissionError,
    VerifiedArtifactReference,
    VerifiedRegistrySnapshot,
    canonicalize_payload,
    sha256_hex,
)
from scope_allocation_schema import validate as validate_schema_contract


MIGRATION_PATH = Path(__file__).with_name("migrations") / "002_scope_allocation.sql"
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
COMMAND_FIELDS = frozenset(
    {"command_type", "deployment_id", "workspace_id", "setup_artifact_id"}
)
FAULT_POINTS = frozenset({"consumption", "allocation", "ledger", "audit", "receipt"})
TABLES = (
    "scope_setup_consumption",
    "scope_allocation",
    "scope_allocation_ledger",
    "scope_allocation_audit",
    "scope_receipt_payload",
)


@dataclass(frozen=True)
class ScopeAllocationCommand:
    command_type: str
    deployment_id: str
    workspace_id: str
    setup_artifact_id: str

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> ScopeAllocationCommand:
        if not isinstance(raw, dict) or set(raw) != COMMAND_FIELDS:
            raise AdmissionError("pre-admission command fields are invalid")
        if raw["command_type"] != "ScopeAllocationCommand":
            raise AdmissionError("unknown pre-admission command")
        if any(
            not isinstance(raw[field], str) or not ID_RE.fullmatch(raw[field])
            for field in ("deployment_id", "workspace_id", "setup_artifact_id")
        ):
            raise AdmissionError("pre-admission command identity is invalid")
        return cls(**raw)

    def canonical(self) -> dict[str, str]:
        return {
            "command_type": self.command_type,
            "deployment_id": self.deployment_id,
            "workspace_id": self.workspace_id,
            "setup_artifact_id": self.setup_artifact_id,
        }


@dataclass(frozen=True)
class TrustedAllocationContext:
    """BCG-authenticated call context, never accepted from a request body."""

    authenticated_actor_id: str
    session_id: str
    command_id: str
    reason: str
    deployment_id: str
    workspace_id: str

    def canonical(self) -> dict[str, str]:
        return {
            "authenticated_actor_id": self.authenticated_actor_id,
            "session_id": self.session_id,
            "command_id": self.command_id,
            "reason": self.reason,
            "deployment_id": self.deployment_id,
            "workspace_id": self.workspace_id,
        }


class ScopeAllocationStore:
    """One local transaction; receipt signing/delivery occurs strictly after commit."""

    def __init__(
        self,
        conninfo: str,
        *,
        connect: Callable[..., Any] = psycopg.connect,
        new_id: Callable[[], uuid.UUID] = uuid.uuid4,
        connect_timeout_seconds: int = 3,
        operation_timeout_ms: int = 3000,
    ) -> None:
        if not isinstance(conninfo, str) or not conninfo:
            raise AdmissionError("scope allocation database configuration is missing")
        if connect_timeout_seconds < 1 or not 1 <= operation_timeout_ms <= 60_000:
            raise AdmissionError("scope allocation timeout is invalid")
        self.conninfo = conninfo
        self._connect = connect
        self._new_id = new_id
        self._connect_timeout_seconds = connect_timeout_seconds
        self._operation_timeout_ms = operation_timeout_ms

    def _connect_db(self) -> Any:
        return self._connect(self.conninfo, connect_timeout=self._connect_timeout_seconds)

    def _timeouts(self, connection: Any) -> None:
        interval = f"{self._operation_timeout_ms}ms"
        connection.execute("SELECT set_config('lock_timeout', %s, true)", (interval,))
        connection.execute("SELECT set_config('statement_timeout', %s, true)", (interval,))

    def migrate(self, admin_conninfo: str) -> None:
        if not isinstance(admin_conninfo, str) or not admin_conninfo:
            raise AdmissionError("scope allocation migration authority is missing")
        try:
            with self._connect(admin_conninfo, connect_timeout=self._connect_timeout_seconds) as connection:
                self._timeouts(connection)
                connection.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
                validate_schema_contract(connection)
        except Exception:
            raise AdmissionError("scope allocation migration failed") from None

    @staticmethod
    def _validate_runtime_role(connection: Any) -> None:
        row = connection.execute(
            """
            SELECT rolsuper, rolcreatedb, rolcreaterole,
                   has_schema_privilege(current_user, 'class_os_gate', 'CREATE'),
                   has_schema_privilege(current_user, 'class_os_gate', 'USAGE')
            FROM pg_roles WHERE rolname = current_user
            """
        ).fetchone()
        if row is None or any(row[:4]) or row[4] is not True:
            raise AdmissionError("scope allocation requires a restricted runtime writer")
        for table in TABLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"):
                granted = connection.execute(
                    "SELECT has_table_privilege(current_user, %s, %s)",
                    (f"class_os_gate.{table}", privilege),
                ).fetchone()[0]
                if granted is not (privilege in ("SELECT", "INSERT")):
                    raise AdmissionError("scope allocation runtime writer privilege mismatch")
        sequence = "class_os_gate.scope_allocation_ledger_sequence"
        for privilege in ("USAGE", "SELECT", "UPDATE"):
            granted = connection.execute(
                "SELECT has_sequence_privilege(current_user, %s, %s)",
                (sequence, privilege),
            ).fetchone()[0]
            if granted is not (privilege == "USAGE"):
                raise AdmissionError("scope allocation runtime writer sequence privilege mismatch")

    @staticmethod
    def _verified_inputs(
        command: ScopeAllocationCommand,
        setup: VerifiedArtifactReference,
        registry: VerifiedRegistrySnapshot,
        now: datetime,
        context: TrustedAllocationContext,
    ) -> tuple[dict[str, Any], str]:
        if not isinstance(command, ScopeAllocationCommand):
            raise AdmissionError("only ScopeAllocationCommand is admitted before final approval")
        if ScopeAllocationCommand.parse(command.canonical()) != command:
            raise AdmissionError("pre-admission command was not validly constructed")
        if not isinstance(setup, VerifiedArtifactReference) or not isinstance(registry, VerifiedRegistrySnapshot):
            raise AdmissionError("scope setup and registry must be verified")
        if now.tzinfo is None or now >= registry.expires_at:
            raise AdmissionError("verified registry snapshot expired")
        if (
            setup.artifact_type != "real-data-scope-setup"
            or setup.lifecycle != "one-time-capability"
            or setup.artifact_id != command.setup_artifact_id
            or setup.registry_generation != registry.generation
            or setup.registry_sha256 != registry.sha256
            or not {"product", "privacy", "security", "operations"}.issubset(setup.verified_roles)
            or not HEX64_RE.fullmatch(setup.digest)
            or sha256_hex(setup.canonical_payload) != setup.digest
        ):
            raise AdmissionError("verified scope setup binding mismatch")
        try:
            payload = json.loads(setup.canonical_payload)
            if not isinstance(payload, dict) or canonicalize_payload(payload) != setup.canonical_payload:
                raise AdmissionError("verified scope setup payload is not canonical")
            expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise AdmissionError("verified scope setup payload is invalid") from None
        owners = payload.get("owner_ids")
        if (
            not isinstance(payload, dict)
            or payload.get("artifact_id") != command.setup_artifact_id
            or payload.get("deployment_id") != command.deployment_id
            or payload.get("workspace_id") != command.workspace_id
            or payload.get("allowed_operation") != "allocate-workspace-bound-empty-scope-only"
            or payload.get("maximum_allocations") != 1
            or not isinstance(owners, list)
            or not owners
            or any(not isinstance(owner, str) or not ID_RE.fullmatch(owner) for owner in owners)
            or len(set(owners)) != len(owners)
            or expires_at.tzinfo is None
            or now >= expires_at
        ):
            raise AdmissionError("scope setup is outside the requested allocation scope")
        if (
            not isinstance(context, TrustedAllocationContext)
            or context.deployment_id != command.deployment_id
            or context.workspace_id != command.workspace_id
            or context.authenticated_actor_id not in owners
            or any(
                not isinstance(value, str) or not value or len(value) > 256
                for value in context.canonical().values()
            )
        ):
            raise AdmissionError("authenticated allocation owner context mismatch")
        request_sha256 = sha256_hex(
            canonicalize_payload({
                "command": command.canonical(),
                "trusted_context": context.canonical(),
                "setup_sha256": setup.digest,
            })
        )
        return payload, request_sha256

    def allocate(
        self,
        command: ScopeAllocationCommand,
        setup: VerifiedArtifactReference,
        registry: VerifiedRegistrySnapshot,
        now: datetime,
        context: TrustedAllocationContext,
        *,
        fault_after: str | None = None,
    ) -> dict[str, Any]:
        if fault_after is not None and fault_after not in FAULT_POINTS:
            raise AdmissionError("unknown fault injection point")
        payload, request_sha256 = self._verified_inputs(command, setup, registry, now, context)
        failed = False
        try:
            with self._connect_db() as connection:
                self._timeouts(connection)
                validate_schema_contract(connection)
                self._validate_runtime_role(connection)
                inserted = connection.execute(
                    """
                    INSERT INTO class_os_gate.scope_setup_consumption
                        (deployment_id, setup_artifact_id, setup_payload_sha256,
                         request_sha256, registry_generation, registry_sha256,
                         workspace_id, owner_ids, consumed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT DO NOTHING RETURNING setup_artifact_id
                    """,
                    (command.deployment_id, command.setup_artifact_id, setup.digest,
                     request_sha256, registry.generation, registry.sha256,
                     command.workspace_id, json.dumps(payload["owner_ids"]), now),
                ).fetchone()
                if inserted is None:
                    existing = connection.execute(
                        """
                        SELECT to_jsonb(c), to_jsonb(a), to_jsonb(l),
                               to_jsonb(au), to_jsonb(r)
                        FROM class_os_gate.scope_setup_consumption AS c
                        LEFT JOIN class_os_gate.scope_allocation AS a
                          ON (a.deployment_id, a.setup_artifact_id) =
                             (c.deployment_id, c.setup_artifact_id)
                        LEFT JOIN class_os_gate.scope_allocation_ledger AS l
                          ON (l.deployment_id, l.setup_artifact_id) =
                             (c.deployment_id, c.setup_artifact_id)
                        LEFT JOIN class_os_gate.scope_allocation_audit AS au
                          ON (au.deployment_id, au.setup_artifact_id, au.ledger_sequence) =
                             (c.deployment_id, c.setup_artifact_id, l.ledger_sequence)
                        LEFT JOIN class_os_gate.scope_receipt_payload AS r
                          ON (r.deployment_id, r.setup_artifact_id, r.ledger_sequence) =
                             (c.deployment_id, c.setup_artifact_id, l.ledger_sequence)
                        WHERE c.deployment_id = %s AND c.setup_artifact_id = %s
                        """,
                        (command.deployment_id, command.setup_artifact_id),
                    ).fetchone()
                    return self._existing_receipt(
                        existing, command, setup, registry, payload, request_sha256
                    )
                self._fault("consumption", fault_after)

                class_id = f"class-{self._new_id().hex}"
                term_id = f"term-{self._new_id().hex}"
                connection.execute(
                    """
                    INSERT INTO class_os_gate.scope_allocation
                        (deployment_id, setup_artifact_id, workspace_id, owner_ids,
                         reserved_class_id, reserved_term_id, allocated_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                    """,
                    (command.deployment_id, command.setup_artifact_id, command.workspace_id,
                     json.dumps(payload["owner_ids"]), class_id, term_id, now),
                )
                self._fault("allocation", fault_after)

                sequence = connection.execute(
                    "SELECT nextval('class_os_gate.scope_allocation_ledger_sequence')"
                ).fetchone()[0]
                entry = {
                    "ledger_sequence": sequence,
                    "deployment_id": command.deployment_id,
                    "setup_artifact_id": command.setup_artifact_id,
                    "workspace_id": command.workspace_id,
                    "request_sha256": request_sha256,
                    "registry_generation": registry.generation,
                    "registry_sha256": registry.sha256,
                }
                entry_hash = sha256_hex(canonicalize_payload(entry))
                connection.execute(
                    """
                    INSERT INTO class_os_gate.scope_allocation_ledger
                        (ledger_sequence, deployment_id, setup_artifact_id,
                         entry, entry_sha256, recorded_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (sequence, command.deployment_id, command.setup_artifact_id,
                     json.dumps(entry), entry_hash, now),
                )
                self._fault("ledger", fault_after)

                connection.execute(
                    """
                    INSERT INTO class_os_gate.scope_allocation_audit
                        (deployment_id, setup_artifact_id, ledger_sequence,
                         event_type, request_sha256, recorded_at)
                    VALUES (%s, %s, %s, 'scope-allocated', %s, %s)
                    """,
                    (command.deployment_id, command.setup_artifact_id,
                     sequence, request_sha256, now),
                )
                self._fault("audit", fault_after)

                receipt = {
                    "setup_artifact_id": command.setup_artifact_id,
                    "deployment_id": command.deployment_id,
                    "workspace_id": command.workspace_id,
                    "owner_ids": payload["owner_ids"],
                    "reserved_class_ids": [class_id],
                    "reserved_term_ids": [term_id],
                    "environment_digest": payload["environment_digest"],
                    "ledger_sequence": sequence,
                    "ledger_entry_sha256": entry_hash,
                    "allocated_at": now.isoformat().replace("+00:00", "Z"),
                }
                receipt_hash = sha256_hex(canonicalize_payload(receipt))
                connection.execute(
                    """
                    INSERT INTO class_os_gate.scope_receipt_payload
                        (deployment_id, setup_artifact_id, ledger_sequence,
                         payload, payload_sha256, committed_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (command.deployment_id, command.setup_artifact_id,
                     sequence, json.dumps(receipt), receipt_hash, now),
                )
                self._fault("receipt", fault_after)
                return receipt
        except AdmissionError:
            raise
        except RuntimeError:
            if fault_after is not None:
                raise
            failed = True
        except Exception:
            failed = True
        if failed:
            raise AdmissionError("scope allocation transaction unavailable")
        raise AssertionError("unreachable scope allocation state")

    def allocate_and_deliver(
        self,
        command: ScopeAllocationCommand,
        setup: VerifiedArtifactReference,
        registry: VerifiedRegistrySnapshot,
        now: datetime,
        context: TrustedAllocationContext,
        *,
        deliver: Callable[[dict[str, Any]], Any],
    ) -> Any:
        receipt = self.allocate(command, setup, registry, now, context)
        return deliver(receipt)

    @staticmethod
    def _existing_receipt(
        existing: tuple[Any, ...] | None,
        command: ScopeAllocationCommand,
        setup: VerifiedArtifactReference,
        registry: VerifiedRegistrySnapshot,
        setup_payload: dict[str, Any],
        request_sha256: str,
    ) -> dict[str, Any]:
        if existing is None or len(existing) != 5 or any(row is None for row in existing):
            raise AdmissionError("scope setup conflict or incomplete transaction")
        consumption, allocation, ledger, audit, receipt_row = existing
        if (
            consumption["setup_payload_sha256"] != setup.digest
            or consumption["request_sha256"] != request_sha256
            or consumption["registry_generation"] != registry.generation
            or consumption["registry_sha256"] != registry.sha256
        ):
            raise AdmissionError("scope setup replay conflict")
        key = (command.deployment_id, command.setup_artifact_id)
        if any((row["deployment_id"], row["setup_artifact_id"]) != key for row in existing):
            raise AdmissionError("scope setup transaction scope mismatch")
        if (
            consumption["workspace_id"] != command.workspace_id
            or allocation["workspace_id"] != command.workspace_id
            or consumption["owner_ids"] != setup_payload["owner_ids"]
            or allocation["owner_ids"] != setup_payload["owner_ids"]
            or audit["event_type"] != "scope-allocated"
            or audit["request_sha256"] != request_sha256
            or audit["ledger_sequence"] != ledger["ledger_sequence"]
            or receipt_row["ledger_sequence"] != ledger["ledger_sequence"]
            or sha256_hex(canonicalize_payload(ledger["entry"])) != ledger["entry_sha256"]
            or ledger["entry"].get("request_sha256") != request_sha256
            or ledger["entry"].get("registry_generation") != registry.generation
            or ledger["entry"].get("registry_sha256") != registry.sha256
        ):
            raise AdmissionError("scope setup transaction evidence mismatch")
        receipt = receipt_row["payload"]
        if (
            sha256_hex(canonicalize_payload(receipt)) != receipt_row["payload_sha256"]
            or receipt.get("workspace_id") != command.workspace_id
            or receipt.get("owner_ids") != setup_payload["owner_ids"]
            or receipt.get("reserved_class_ids") != [allocation["reserved_class_id"]]
            or receipt.get("reserved_term_ids") != [allocation["reserved_term_id"]]
            or receipt.get("ledger_sequence") != ledger["ledger_sequence"]
            or receipt.get("ledger_entry_sha256") != ledger["entry_sha256"]
            or receipt.get("environment_digest") != setup_payload["environment_digest"]
        ):
            raise AdmissionError("stored scope receipt payload was altered")
        return receipt

    def counts(self, deployment_id: str, setup_artifact_id: str) -> tuple[int, ...]:
        if not ID_RE.fullmatch(deployment_id) or not ID_RE.fullmatch(setup_artifact_id):
            raise AdmissionError("scope allocation count identity is invalid")
        try:
            with self._connect_db() as connection:
                return tuple(
                    connection.execute(
                        f"SELECT count(*) FROM class_os_gate.{table} "
                        "WHERE deployment_id = %s AND setup_artifact_id = %s",
                        (deployment_id, setup_artifact_id),
                    ).fetchone()[0]
                    for table in TABLES
                )
        except Exception:
            raise AdmissionError("scope allocation ledger unavailable") from None

    @staticmethod
    def _fault(point: str, selected: str | None) -> None:
        if selected == point:
            raise RuntimeError("injected precommit failure")
