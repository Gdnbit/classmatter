"""Exact PostgreSQL schema fingerprint for the synthetic scope transaction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signature_envelope import AdmissionError


ROOT = Path(__file__).resolve().parent
GOLDEN = ROOT / "migrations/002_scope_allocation.schema.json"
NAMES = (
    "scope_setup_consumption", "scope_allocation", "scope_allocation_ledger",
    "scope_allocation_audit", "scope_receipt_payload",
    "scope_allocation_ledger_sequence",
)


def snapshot(connection: Any) -> dict[str, Any]:
    relations = connection.execute(
        """
        SELECT c.relname, c.relkind, c.relpersistence, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'class_os_gate' AND c.relname = ANY(%s)
        ORDER BY c.relname
        """, (list(NAMES),)
    ).fetchall()
    columns = connection.execute(
        """
        SELECT c.relname, a.attnum, a.attname, format_type(a.atttypid, a.atttypmod),
               a.attnotnull, pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated
        FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
        JOIN pg_attribute AS a ON a.attrelid = c.oid
        LEFT JOIN pg_attrdef AS d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE n.nspname = 'class_os_gate' AND c.relname = ANY(%s)
          AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY c.relname, a.attnum
        """, (list(NAMES),)
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT t.relname, c.conname, c.contype, c.convalidated, c.condeferrable,
               c.condeferred, pg_get_constraintdef(c.oid, true)
        FROM pg_constraint AS c JOIN pg_class AS t ON t.oid = c.conrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'class_os_gate' AND t.relname = ANY(%s)
        ORDER BY t.relname, c.conname
        """, (list(NAMES),)
    ).fetchall()
    triggers = connection.execute(
        """
        SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid, true)
        FROM pg_trigger AS t JOIN pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'class_os_gate' AND c.relname = ANY(%s)
          AND NOT t.tgisinternal
        ORDER BY c.relname, t.tgname
        """, (list(NAMES),)
    ).fetchall()
    rules = connection.execute(
        """
        SELECT c.relname, r.rulename, pg_get_ruledef(r.oid, true)
        FROM pg_rewrite AS r JOIN pg_class AS c ON c.oid = r.ev_class
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'class_os_gate' AND c.relname = ANY(%s)
          AND r.rulename <> '_RETURN'
        ORDER BY c.relname, r.rulename
        """, (list(NAMES),)
    ).fetchall()
    policies = connection.execute(
        """
        SELECT c.relname, p.polname, p.polcmd, pg_get_expr(p.polqual, p.polrelid),
               pg_get_expr(p.polwithcheck, p.polrelid)
        FROM pg_policy AS p JOIN pg_class AS c ON c.oid = p.polrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'class_os_gate' AND c.relname = ANY(%s)
        ORDER BY c.relname, p.polname
        """, (list(NAMES),)
    ).fetchall()
    indexes = connection.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes WHERE schemaname = 'class_os_gate' AND tablename = ANY(%s)
        ORDER BY tablename, indexname
        """, (list(NAMES),)
    ).fetchall()
    sequence = connection.execute(
        """
        SELECT sequencename, data_type, start_value, min_value, max_value,
               increment_by, cycle, cache_size
        FROM pg_sequences
        WHERE schemaname = 'class_os_gate' AND sequencename = 'scope_allocation_ledger_sequence'
        """
    ).fetchall()
    function = connection.execute(
        """
        SELECT pg_get_functiondef(p.oid)
        FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'class_os_gate'
          AND p.proname = 'reject_scope_allocation_mutation'
        """
    ).fetchall()
    return {
        "relations": [list(row) for row in relations],
        "columns": [list(row) for row in columns],
        "constraints": [list(row) for row in constraints],
        "triggers": [list(row) for row in triggers],
        "rules": [list(row) for row in rules],
        "policies": [list(row) for row in policies],
        "indexes": [list(row) for row in indexes],
        "sequence": [list(row) for row in sequence],
        "function": [list(row) for row in function],
    }


def validate(connection: Any) -> None:
    try:
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise AdmissionError("scope allocation schema contract is missing") from None
    if snapshot(connection) != expected:
        raise AdmissionError("scope allocation schema contract mismatch")
