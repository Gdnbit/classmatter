"""Row-bounded source reads reject overflow, never publish a partial exit."""
from datetime import datetime, timezone
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from class_os.domain.exit_package import CORE_COLUMNS, CreateExitExport
from class_os.infrastructure.exit_package import ExitTransaction
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.parametrize("surface", ["core", "audit"])
def test_overflow_sentinel_is_db_bounded_and_never_published(surface):
    statements, writes = [], []
    class Overflow:
        def execute(self, statement, values):
            statements.append(str(statement))
            assert re.search(r"\bLIMIT\s+10001\b", str(statement), re.I), "Unbounded exit source read"
            return self
        def mappings(self):
            return self
        def all(self):
            return [{}] * 10001
    class Adapter(ExitTransaction):
        _connection = Overflow()
        def _mutate(self, *args):
            writes.append(True)
            pytest.fail("Overflow must not publish a partial exit")
    adapter = Adapter()
    if surface == "core":
        with pytest.raises(ValueError, match="Core export exceeds"):
            adapter.core_snapshot(uuid4())
    else:
        adapter.core_snapshot = lambda workspace: {}
        with pytest.raises(ValueError, match="Audit export exceeds"):
            adapter.create_exit({"workspace_id": uuid4(), "actor_id": uuid4()}, SimpleNamespace(export_id=uuid4()), datetime.now(timezone.utc))
    assert len(statements) == 1 and writes == []


@pytest.mark.db
def test_actual_core_and_audit_queries_use_sentinel_and_preserve_complete_package(roster):
    business, query, store, auth, _, _, _ = roster
    _, _, record = seed(roster)
    submit(business, auth, record)
    summary = query.exit_summary(*auth)
    command = CreateExitExport(uuid4(), summary.core_hash)
    preview = business.preview(*auth, command)
    approval = business.approve(*auth, preview.proposal_id, preview.payload_hash)
    captured = []
    def observe(connection, cursor, statement, parameters, context, many):
        if re.match(r"\s*SELECT workspace_id,", statement, re.I):
            captured.append(statement)
    event.listen(store.database.engine, "before_cursor_execute", observe)
    try:
        receipt = business.commit(*auth, preview.proposal_id, uuid4(), approval)
    finally:
        event.remove(store.database.engine, "before_cursor_execute", observe)
    # Validation re-reads all8core tables, then creation re-reads8+audit refs.
    assert len(captured) == len(CORE_COLUMNS) * 2 + 1
    assert all(re.search(r"\bLIMIT\s+10001\b", statement, re.I) for statement in captured)
    artifact = query.exit_download(*auth, receipt.resource_id)
    assert artifact.bundle["core_checksum"] == summary.core_hash
    assert {table: len(rows) for table, rows in artifact.bundle["core"].items()} == summary.counts
    assert len(artifact.bundle["core"]["record_revision"]) == 1
    assert artifact.bundle["lifecycle_status"]["complete"] is False
