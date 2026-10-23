"""Real browser against real disposable PostgreSQL, no mocked network routes."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
import uvicorn
from sqlalchemy import text

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from class_os.infrastructure.agent import PydanticAgentRuntime
from test_roster_gateway import roster
from test_identity import identity
from test_model_secrets import fixture_codec
from class_os.infrastructure.model_secrets import ModelSecrets
from class_os.infrastructure.model_control import ModelController
from test_agent_api_protocol import protocol_reply, MODEL
from openai import AsyncOpenAI
from contextlib import asynccontextmanager
import json


@pytest.mark.db
def test_real_browser_direct_ui_record_task_and_reload(roster):
    business, query, _, _, boundary, owner, clock = roster
    started = time.monotonic()
    # Browser actions advance from a synthetic anchor, never host wall time.
    # A frozen clock would make enrollment creation/deactivation simultaneous.
    def browser_clock():
        return clock[0] + timedelta(seconds=time.monotonic() - started)
    business.clock = query.clock = boundary.clock = browser_clock
    first_history = threading.Event()
    original_history = query.history
    def slow_first_history(*args):
        if not first_history.is_set():
            first_history.set()
            time.sleep(1)  # Owned latency injection; still calls real QG/DB.
        return original_history(*args)
    query.history = slow_first_history
    lost_commit_response = threading.Event()
    original_commit = business.commit
    def commit_with_owned_delivery_fault(*args):
        receipt = original_commit(*args)  # Real BCG/PG commit and audit first.
        with owner.transaction(read_only=True) as connection:
            title = connection.execute(text("SELECT title FROM class_os.manual_task WHERE task_id=:id"),
                                       {"id": receipt.resource_id}).scalar_one_or_none()
        if title == "合成 Agent 未提交任务" and not lost_commit_response.is_set():
            lost_commit_response.set()
            raise RuntimeError("Synthetic post-commit response delivery outage")
        return receipt
    business.commit = commit_with_owned_delivery_fault
    lost_identity_response = threading.Event()
    identity_reissues = []
    original_reissue = boundary.reissue_recovery
    def reissue_with_owned_output_fault(*args):
        identity_reissues.append(True)
        result = original_reissue(*args)
        if not lost_identity_response.is_set():
            lost_identity_response.set()
            return replace(result, recovery_codes=())
        return result
    boundary.reissue_recovery = reissue_with_owned_output_fault
    failed_logout_request = threading.Event()
    lost_logout_response = threading.Event()
    logout_requests = []
    original_logout = boundary.logout
    def logout_with_owned_preexecution_fault(*args):
        logout_requests.append(True)
        if not failed_logout_request.is_set():
            failed_logout_request.set()
            raise RuntimeError("Synthetic preexecution identity outage")
        result = original_logout(*args)
        if not lost_logout_response.is_set():
            lost_logout_response.set()
            raise RuntimeError("Synthetic postcommit logout delivery outage")
        return result
    boundary.logout = logout_with_owned_preexecution_fault
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    vault = ModelSecrets(fixture_codec, clock=browser_clock)
    business.store.model_secrets = vault
    agent = PydanticAgentRuntime(query)
    model_calls = []
    @asynccontextmanager
    async def model_client(profile, key):
        def reply(request):
            assert request.headers["authorization"] == "Bearer synthetic-browser-api-secret"
            model_calls.append(request)
            return httpx.Response(200, json=protocol_reply(profile.protocol.value, json.loads(request.content), len(model_calls)))
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False) as http:
            async with AsyncOpenAI(api_key=key.get_secret_value(), base_url=profile.base_url,
                                   organization="", project="", max_retries=0, http_client=http) as client:
                yield client
    controller = ModelController(query, vault, agent, allowed_bases=("https://provider.example.invalid/v1",),
                                 client_factory=model_client, clock=browser_clock)
    agent.model_context, agent.provider_state = controller.context, controller.label
    app = create_app(Settings(port=port), identity=boundary, business=business, query=query, agent=agent, model_controller=controller)
    mount_web(app, root / "apps/web/dist")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False,
                                          log_level="error", proxy_headers=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        with httpx.Client(trust_env=False) as client:
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline
                time.sleep(.05)
            assert client.get(f"http://127.0.0.1:{port}/").status_code == 200
            assert client.get(f"http://127.0.0.1:{port}/api/not-real").status_code == 404
        result = subprocess.run(["node", "tests/runtime.mjs"], cwd=root / "apps/web",
                                env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}"),
                                timeout=130, capture_output=True, text=True, encoding="utf-8",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert lost_commit_response.is_set()
        assert lost_identity_response.is_set() and len(identity_reissues) == 2
        assert failed_logout_request.is_set()
        assert lost_logout_response.is_set() and len(logout_requests) == 2
        assert len(model_calls) == 4, "Exactly one SDK protocol test and one actual read run; no save/enable/disable network calls"
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        assert not thread.is_alive(), "Owned browser fixture listener did not stop"
