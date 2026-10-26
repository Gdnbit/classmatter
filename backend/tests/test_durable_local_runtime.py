"""Actual owned DPAPI/PG D1 assembly; never touches a user's runtime."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
import pytest

from class_os.application.identity import IdentityBoundary
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.local_runtime import LocalRuntime
from class_os.infrastructure.durable_local_runtime import open_services, compose
from class_os.infrastructure.operator_backup import SyntheticBackup
from class_os.interfaces.http.settings import Settings
from test_identity import setup, CLIENT


def test_cli_control_requires_explicit_profile_and_real_interactive_owner():
    root = Path(__file__).resolve().parents[1]
    for arguments in (("initialize-control",), ("initialize-control", "--profile", "conversation-d1")):
        result = subprocess.run([sys.executable, "local.py", *arguments], cwd=root, input="",
            capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode != 0
        assert "Traceback" not in result.stderr and "password:" not in result.stdout.lower()
        assert "Current Owner password" not in result.stdout
    result = subprocess.run([sys.executable, "local.py", "--help"], cwd=root,
        capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0 and "conversation-d1" in result.stdout


def test_owned_d1_assembly_cannot_reinterpret_default_r1():
    with pytest.raises(ValueError):
        open_services(LocalRuntime())


@pytest.mark.parametrize("profile,configured,expected", [("r1", None, 8000), ("conversation-d1", None, 8001), ("conversation-d1", "8012", 8012)])
def test_cli_serve_port_defaults_are_profile_bound_without_starting_a_service(monkeypatch, profile, configured, expected):
    import runpy
    import uvicorn
    from class_os.infrastructure import durable_local_runtime, local_runtime
    from class_os.interfaces.http import web
    captured = []
    def fake_compose(settings, runtime):
        captured.append((settings.port, runtime.profile))
        return object()
    monkeypatch.setattr(local_runtime, "compose", fake_compose)
    monkeypatch.setattr(durable_local_runtime, "compose", fake_compose)
    monkeypatch.setattr(web, "mount_web", lambda *args: None)
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: captured.append(options["port"]))
    monkeypatch.delenv("CLASS_OS_PORT", raising=False)
    if configured is not None: monkeypatch.setenv("CLASS_OS_PORT", configured)
    monkeypatch.setattr(sys, "argv", ["local.py", "serve", "--profile", profile])
    cli = runpy.run_path(str(Path(__file__).resolve().parents[1] / "local.py"))
    cli["main"]()
    assert captured == [(expected, profile), expected]


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Owned Windows DPAPI runtime")
def test_owned_d1_owner_control_http_restart_backup_and_corrupt_witness_fail_closed(tmp_path, request):
    runtime = LocalRuntime(tmp_path / "owned-d1-composition", profile="conversation-d1")
    runtime.initialize(request.config.getoption("--pg-root"))
    services, running = None, False
    try:
        runtime.start(); running = True
        with pytest.raises(RuntimeError, match="Owner"):
            open_services(runtime)
        identity_db = runtime.database("identity")
        try:
            boundary = IdentityBoundary(PostgresIdentityStore(identity_db), PasswordHash.recommended())
            login = setup(boundary)  # Synthetic test Owner in ONLY this disposable cluster.
        finally:
            identity_db.close()
        services = open_services(runtime)
        with pytest.raises(RuntimeError):
            services.readiness()
        with pytest.raises(RuntimeError):
            compose(Settings(), runtime)
        assert not (runtime.root / "conversation-restrictions.dpapi").exists()
        auth = (login.token, CLIENT, login.csrf, login.subject.workspace_id)
        proposal = services.worker.preview(*auth, InitializeConversationControl(uuid4()))
        assert proposal.risk == "X"
        approval = services.worker.approve(*auth, proposal.proposal_id, proposal.payload_hash)
        services.worker.commit(*auth, proposal.proposal_id, uuid4(), approval)
        services.readiness()
        backup = SyntheticBackup(runtime, profile="conversation-d1")
        artifact = backup.create()
        checked = backup.check_current_restrictions(artifact, services.restrictions)
        assert checked["snapshot_integrity_verified"] and checked["current_restrictions_verified_at_check"]
        assert checked["activation_allowed"] is False and checked["table_count"] == 35
        for _ in range(2):
            app = compose(Settings(), runtime)
            with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 1234)) as api:
                for name, value in zip(("session", "client", "csrf"), auth[:3]):
                    api.cookies.set("class_os_" + name, value, path="/api")
                assert api.get("/health/ready").status_code == 200
                capability = api.get(f"/api/workspaces/{auth[3]}/conversation-d1/capabilities")
                assert capability.status_code == 200, capability.text
                assert capability.json()["data_mode"] == "synthetic-only"
            services.close(); services = None
            runtime.stop(); running = False
            runtime.start(); running = True
            services = open_services(runtime)
            services.readiness()
        app = compose(Settings(), runtime)
        witness = runtime.root / "conversation-restrictions.dpapi"
        witness.write_bytes(b"synthetic-corrupt-witness")
        with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 1234)) as api:
            assert api.get("/health/ready").status_code == 503
        with pytest.raises(Exception):
            compose(Settings(), runtime)
        assert witness.read_bytes() == b"synthetic-corrupt-witness"  # No automatic repair/reset.
    finally:
        if services is not None:
            services.close()
        if running:
            runtime.stop()
