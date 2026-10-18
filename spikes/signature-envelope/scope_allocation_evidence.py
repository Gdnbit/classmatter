"""Fail-closed drift check for the isolated live scope allocation drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence/scope-allocation.latest.json"
SOURCES = {
    "scope_allocation.py": ROOT / "scope_allocation.py",
    "scope_allocation_schema.py": ROOT / "scope_allocation_schema.py",
    "scope_allocation_drill.py": ROOT / "scope_allocation_drill.py",
    "scope_allocation_evidence.py": ROOT / "scope_allocation_evidence.py",
    "tests/test_scope_allocation.py": ROOT / "tests/test_scope_allocation.py",
    "tests/test_scope_allocation_evidence.py": ROOT / "tests/test_scope_allocation_evidence.py",
    "../self-host/portable_recovery.py": ROOT.parent / "self-host/portable_recovery.py",
}
LIMITATIONS = [
    "One isolated local PostgreSQL cluster and synthetic setup records only.",
    "VerifiedSetup input is a trusted-port test fixture, not live DSSE approval or production signing.",
    "This is transaction evidence, not complete E-ADM-001—009 or BCG adapter-bypass evidence.",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(document: Any) -> None:
    if not isinstance(document, dict):
        raise ValueError("scope allocation evidence is not an object")
    if (
        document.get("schema") != "class-os.synthetic-scope-allocation-transaction-evidence/v1"
        or document.get("synthetic_only") is not True
        or document.get("production_authorization") is not False
        or document.get("restart_projection_equal") is not True
        or document.get("outage_failed_closed") is not True
        or document.get("cleanup_completed_before_evidence_write") is not True
        or document.get("limitations") != LIMITATIONS
    ):
        raise ValueError("scope allocation evidence claims are incomplete")
    counts = document.get("five_member_row_counts")
    if (
        not isinstance(counts, list)
        or len(counts) != 5
        or any(type(count) is not int or count < 1 for count in counts)
        or len(set(counts)) != 1
    ):
        raise ValueError("scope allocation transaction row counts differ")
    if not isinstance(document.get("live_test_result"), str) or not re.fullmatch(
        r"[1-9][0-9]* passed in [0-9]+(?:\.[0-9]+)?s", document["live_test_result"]
    ):
        raise ValueError("scope allocation live tests did not pass without skips")
    if document.get("migration_sha256") != sha(ROOT / "migrations/002_scope_allocation.sql"):
        raise ValueError("scope allocation migration evidence drift")
    if document.get("schema_contract_sha256") != sha(ROOT / "migrations/002_scope_allocation.schema.json"):
        raise ValueError("scope allocation schema contract evidence drift")
    projection_sha256 = document.get("five_table_projection_sha256")
    if not isinstance(projection_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", projection_sha256):
        raise ValueError("scope allocation five-table projection is missing")
    if document.get("source_sha256") != {name: sha(path) for name, path in SOURCES.items()}:
        raise ValueError("scope allocation source evidence drift")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("check",))
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    try:
        validate(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"scope allocation evidence invalid: {exc}") from None
    print("scope allocation live PostgreSQL evidence matches source and migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
