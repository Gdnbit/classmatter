"""Real D1 Electron and PG process restarts, using only a fresh owned root."""
import os
from pathlib import Path
import socket
import subprocess
from uuid import uuid4

from pwdlib import PasswordHash
import pytest
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.local_runtime import LocalRuntime
from class_os.infrastructure.durable_local_runtime import open_services
from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows Electron/owned DPAPI runtime")
def test_d1_desktop_and_pg_restart_restore_source_then_clear_blocks_old_backup(tmp_path, request):
    root = Path(__file__).resolve().parents[2]
    desktop = root / "apps/desktop"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    built = subprocess.run(["node", "scripts/runtime-build.cjs", "--profile", "conversation-d1"],
        cwd=desktop, capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert built.returncode == 0, "D1 desktop build failed; no runtime changed"
    runtime = LocalRuntime(tmp_path / "actual-desktop-d1", profile="conversation-d1")
    runtime.initialize(request.config.getoption("--pg-root"))
    services, running = None, False
    try:
        runtime.start(); running = True
        identity_db = runtime.database("identity")
        try:
            boundary = IdentityBoundary(PostgresIdentityStore(identity_db), PasswordHash.recommended())
            client = "synthetic-owned-d1-desktop-client"
            owner = boundary.bootstrap(boundary.arm_bootstrap(), "synthetic-test-passphrase-2026", client)
        finally:
            identity_db.close()
        services = open_services(runtime)
        auth = (owner.token, client, owner.csrf, owner.subject.workspace_id)
        proposal = services.worker.preview(*auth, InitializeConversationControl(uuid4()))
        approval = services.worker.approve(*auth, proposal.proposal_id, proposal.payload_hash)
        services.worker.commit(*auth, proposal.proposal_id, uuid4(), approval)
        services.identity.logout(*auth[:3])
        services.close(); services = None
        backup = SyntheticBackup(runtime, profile="conversation-d1")
        checkpoint = None
        for phase in ("create", "restore-clear"):
            result = subprocess.run(["node", "tests/durable-integration.cjs"], cwd=desktop,
                env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(runtime.root),
                    CLASSMATTER_TEST_SERVICE_PORT=str(port), CLASSMATTER_TEST_D1_PHASE=phase),
                capture_output=True, text=True, encoding="utf-8", timeout=130,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert result.returncode == 0, result.stdout + result.stderr
            if phase == "create":
                checkpoint = backup.create()
                runtime.stop(); running = False
                runtime.start(); running = True  # Actual PG OS process, not a replaced in-memory adapter.
        services = open_services(runtime); services.readiness()
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(checkpoint, services.restrictions)
        checked = backup.check_current_restrictions(backup.create(), services.restrictions)
        assert checked["current_restrictions_verified_at_check"] and checked["activation_allowed"] is False
        with services.business_database.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_run WHERE state='completed'")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE body IS NOT NULL")).scalar_one() == 0
    finally:
        if services is not None:
            services.close()
        if running:
            runtime.stop()
