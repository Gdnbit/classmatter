"""Real Electron + owned API + disposable SCRAM PostgreSQL, synthetic only."""
import os
from pathlib import Path
import subprocess
import socket

import pytest
from pwdlib import PasswordHash
from sqlalchemy import text

from class_os.application.identity import IdentityBoundary
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.local_runtime import LocalRuntime


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Windows desktop/DPAPI integration")
def test_owned_desktop_record_task_survive_application_restart(tmp_path, request):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 8000))
        except OSError:
            pytest.skip("Fixed developer port occupied; no existing listener is stopped")
    root = Path(__file__).resolve().parents[2]
    desktop = root / "apps/desktop"
    if not (desktop / "node_modules/electron").is_dir():
        pytest.fail("Install frozen desktop test dependencies first")
    built = subprocess.run(["node", "scripts/runtime-build.cjs"], cwd=desktop, capture_output=True, timeout=40)
    assert built.returncode == 0, "Synthetic desktop build failed"
    runtime = LocalRuntime(tmp_path / "owned-desktop-runtime")
    runtime.initialize(request.config.getoption("--pg-root"))
    runtime.start()
    identity_db = runtime.database("identity")
    try:
        boundary = IdentityBoundary(PostgresIdentityStore(identity_db), PasswordHash.recommended())
        owner = boundary.bootstrap(boundary.arm_bootstrap(), "synthetic-test-passphrase-2026", "synthetic-desktop-fixture-client")
        boundary.logout(owner.token, "synthetic-desktop-fixture-client", owner.csrf)
        result = subprocess.run(["node", "tests/runtime-integration.cjs"], cwd=desktop,
                                env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(runtime.root)),
                                capture_output=True, text=True, encoding="utf-8", timeout=110,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        business_db = runtime.database("runtime")
        try:
            with business_db.transaction(read_only=True) as connection:
                assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 1
                assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 1
        finally:
            business_db.close()
    finally:
        identity_db.close()
        runtime.stop()
