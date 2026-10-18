"""PostgreSQL adapter for durable signed-artifact identity uniqueness."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

import psycopg

from signature_envelope import AdmissionError


MIGRATION_PATH = Path(__file__).with_name("migrations") / "001_artifact_identity_ledger.sql"
ARTIFACT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
NONCE_RE = re.compile(r"[0-9a-f]{32}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")

EXPECTED_COLUMNS = [
    ("artifact_id", "text", "text", None, "NO", None, "NO", "NEVER"),
    ("nonce", "character", "bpchar", 32, "NO", None, "NO", "NEVER"),
    ("payload_digest", "character", "bpchar", 64, "NO", None, "NO", "NEVER"),
    (
        "first_observed_at",
        "timestamp with time zone",
        "timestamptz",
        None,
        "NO",
        "clock_timestamp()",
        "NO",
        "NEVER",
    ),
]
EXPECTED_KEY_CONSTRAINTS = {
    "artifact_identity_ledger_pkey": ("p", ["artifact_id"]),
    "artifact_identity_ledger_nonce_key": ("u", ["nonce"]),
}
EXPECTED_CHECK_PATTERNS = {
    "artifact_identity_ledger_artifact_id_format": (
        "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        ["artifact_id"],
    ),
    "artifact_identity_ledger_nonce_format": ("^[0-9a-f]{32}$", ["nonce"]),
    "artifact_identity_ledger_payload_digest_format": (
        "^[0-9a-f]{64}$",
        ["payload_digest"],
    ),
}

EXPECTED_CHECK_DEFINITIONS = {
    name: f"CHECK ({columns[0]} ~ '{pattern}'::text)"
    for name, (pattern, columns) in EXPECTED_CHECK_PATTERNS.items()
}


def migration_sha256() -> str:
    return hashlib.sha256(MIGRATION_PATH.read_bytes()).hexdigest()


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_contract_snapshot(connection: Any) -> dict[str, Any]:
    columns = connection.execute(
        """
        SELECT column_name, data_type, udt_name, character_maximum_length,
               is_nullable, column_default, is_identity, is_generated
        FROM information_schema.columns
        WHERE table_schema = 'class_os_gate'
          AND table_name = 'artifact_identity_ledger'
        ORDER BY ordinal_position
        """
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT c.conname, c.contype,
               COALESCE(array_agg(a.attname ORDER BY keys.ordinality)
                        FILTER (WHERE a.attname IS NOT NULL), ARRAY[]::name[]),
               pg_get_constraintdef(c.oid, true),
               c.convalidated, c.condeferrable, c.condeferred
        FROM pg_constraint AS c
        JOIN pg_class AS t ON t.oid = c.conrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        LEFT JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS keys(attnum, ordinality) ON true
        LEFT JOIN pg_attribute AS a ON a.attrelid = t.oid AND a.attnum = keys.attnum
        WHERE n.nspname = 'class_os_gate'
          AND t.relname = 'artifact_identity_ledger'
          AND c.contype IN ('p', 'u', 'c')
        GROUP BY c.oid, c.conname, c.contype
        ORDER BY c.conname
        """
    ).fetchall()
    return {
        "columns": [list(row) for row in columns],
        "constraints": [
            [name, kind, list(key_columns), definition, validated, deferrable, deferred]
            for name, kind, key_columns, definition, validated, deferrable, deferred in constraints
        ],
        "table": list(
            connection.execute(
                """
                SELECT c.relkind, c.relpersistence, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'class_os_gate'
                  AND c.relname = 'artifact_identity_ledger'
                """
            ).fetchone()
            or []
        ),
        "user_triggers": [
            row[0]
            for row in connection.execute(
                """
                SELECT tg.tgname
                FROM pg_trigger AS tg
                JOIN pg_class AS c ON c.oid = tg.tgrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'class_os_gate'
                  AND c.relname = 'artifact_identity_ledger'
                  AND NOT tg.tgisinternal
                ORDER BY tg.tgname
                """
            ).fetchall()
        ],
        "rules": [
            row[0]
            for row in connection.execute(
                """
                SELECT r.rulename
                FROM pg_rewrite AS r
                JOIN pg_class AS c ON c.oid = r.ev_class
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'class_os_gate'
                  AND c.relname = 'artifact_identity_ledger'
                  AND r.rulename <> '_RETURN'
                ORDER BY r.rulename
                """
            ).fetchall()
        ],
        "policies": [
            row[0]
            for row in connection.execute(
                """
                SELECT p.polname
                FROM pg_policy AS p
                JOIN pg_class AS c ON c.oid = p.polrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'class_os_gate'
                  AND c.relname = 'artifact_identity_ledger'
                ORDER BY p.polname
                """
            ).fetchall()
        ],
    }


def schema_contract_sha256(connection: Any) -> str:
    payload = json.dumps(
        schema_contract_snapshot(connection), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_schema_contract(connection: Any) -> None:
    snapshot = schema_contract_snapshot(connection)
    if [tuple(row) for row in snapshot["columns"]] != EXPECTED_COLUMNS:
        raise AdmissionError("artifact identity ledger schema contract mismatch")
    if snapshot["table"] != ["r", "p", False, False]:
        raise AdmissionError("artifact identity ledger schema contract mismatch")
    if snapshot["user_triggers"] or snapshot["rules"] or snapshot["policies"]:
        raise AdmissionError("artifact identity ledger schema contract mismatch")

    constraints = {
        name: (kind, key_columns, definition, validated, deferrable, deferred)
        for name, kind, key_columns, definition, validated, deferrable, deferred in snapshot[
            "constraints"
        ]
    }
    if set(constraints) != set(EXPECTED_KEY_CONSTRAINTS) | set(EXPECTED_CHECK_PATTERNS):
        raise AdmissionError("artifact identity ledger schema contract mismatch")
    for name, expected in EXPECTED_KEY_CONSTRAINTS.items():
        kind, key_columns, _definition, validated, deferrable, deferred = constraints[name]
        if (kind, key_columns) != expected or not validated or deferrable or deferred:
            raise AdmissionError("artifact identity ledger schema contract mismatch")
    for name, (_pattern, expected_columns) in EXPECTED_CHECK_PATTERNS.items():
        kind, key_columns, definition, validated, deferrable, deferred = constraints[name]
        if (
            kind != "c"
            or key_columns != expected_columns
            or definition != EXPECTED_CHECK_DEFINITIONS[name]
            or not validated
            or deferrable
            or deferred
        ):
            raise AdmissionError("artifact identity ledger schema contract mismatch")


class PostgresIdentityLedger:
    """Enforce idempotent artifact-id/nonce observations with DB constraints.

    This adapter does not consume one-time capabilities and does not allocate a
    workspace.  Those operations require a larger Business Command Gateway
    transaction.
    """

    def __init__(
        self,
        conninfo: str,
        *,
        connect: Callable[..., Any] = psycopg.connect,
        connect_timeout_seconds: int = 3,
        operation_timeout_ms: int = 3000,
    ) -> None:
        if not isinstance(conninfo, str) or not conninfo:
            raise AdmissionError("identity ledger connection configuration is missing")
        if connect_timeout_seconds < 1:
            raise AdmissionError("identity ledger connect timeout must be positive")
        if operation_timeout_ms < 1 or operation_timeout_ms > 60_000:
            raise AdmissionError("identity ledger operation timeout is invalid")
        self._conninfo = conninfo
        self._connect = connect
        self._connect_timeout_seconds = connect_timeout_seconds
        self._operation_timeout_ms = operation_timeout_ms

    def _set_local_timeouts(self, connection: Any) -> None:
        timeout = f"{self._operation_timeout_ms}ms"
        connection.execute("SELECT set_config('lock_timeout', %s, true)", (timeout,))
        connection.execute("SELECT set_config('statement_timeout', %s, true)", (timeout,))

    def migrate(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        failed = False
        try:
            with self._connect(
                self._conninfo, connect_timeout=self._connect_timeout_seconds
            ) as connection:
                self._set_local_timeouts(connection)
                connection.execute(sql)
                validate_schema_contract(connection)
        except AdmissionError:
            raise
        except Exception:
            failed = True
        if failed:
            raise AdmissionError("artifact identity ledger migration failed")

    def observe(self, artifact_id: str, nonce: str, payload_digest: str) -> None:
        self._validate(artifact_id, nonce, payload_digest)
        failed = False
        try:
            with self._connect(
                self._conninfo, connect_timeout=self._connect_timeout_seconds
            ) as connection:
                self._set_local_timeouts(connection)
                inserted = connection.execute(
                    """
                    INSERT INTO class_os_gate.artifact_identity_ledger
                        (artifact_id, nonce, payload_digest)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING artifact_id, nonce::text, payload_digest::text
                    """,
                    (artifact_id, nonce, payload_digest),
                ).fetchone()
                if inserted is not None:
                    if tuple(inserted) != (artifact_id, nonce, payload_digest):
                        raise AdmissionError("artifact identity ledger write result mismatch")
                    return

                by_id = connection.execute(
                    """
                    SELECT nonce, payload_digest
                    FROM class_os_gate.artifact_identity_ledger
                    WHERE artifact_id = %s
                    """,
                    (artifact_id,),
                ).fetchone()
                if by_id is not None:
                    prior_nonce, prior_digest = by_id
                    if prior_nonce == nonce and prior_digest == payload_digest:
                        return
                    raise AdmissionError("artifact id collision in identity ledger")

                by_nonce = connection.execute(
                    """
                    SELECT artifact_id
                    FROM class_os_gate.artifact_identity_ledger
                    WHERE nonce = %s
                    """,
                    (nonce,),
                ).fetchone()
                if by_nonce is not None:
                    raise AdmissionError("nonce collision in identity ledger")
                raise AdmissionError("identity ledger conflict could not be resolved")
        except AdmissionError:
            raise
        except Exception:
            failed = True
        if failed:
            raise AdmissionError("artifact identity ledger unavailable")

    @staticmethod
    def _validate(artifact_id: str, nonce: str, payload_digest: str) -> None:
        if not isinstance(artifact_id, str) or not ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise AdmissionError("artifact id is invalid")
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise AdmissionError("artifact nonce is invalid")
        if not isinstance(payload_digest, str) or not DIGEST_RE.fullmatch(payload_digest):
            raise AdmissionError("artifact payload digest is invalid")
