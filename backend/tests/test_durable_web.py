"""Real browser/socket/PG D1 UI, no intercepted API or Demo store."""
from datetime import timedelta
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4
from pydantic_ai.messages import ModelResponse, TextPart

import pytest
from sqlalchemy import text
import uvicorn

from class_os.domain.activity import CreateRecord, CreateTask
from class_os.interfaces.http.durable_conversation import create_durable_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_durable_conversation_http import setup
from test_conversation_control import control, storage, roster, identity


@pytest.mark.db
@pytest.mark.parametrize("reauth_phase", ["approve", "commit"])
def test_actual_browser_durable_read_draft_reload_clear_keeps_business_data(control, reauth_phase):
    value = setup(control)
    started = time.monotonic()
    elapsed = [timedelta()]
    now = lambda: control[7][0] + timedelta(seconds=time.monotonic() - started) + elapsed[0]
    value.worker.clock = value.query.clock = value.worker.identity.clock = now
    publish = value.store.restrictions._publish
    published_failure = []
    def publish_then_lose_reply(*args, **kwargs):
        publish(*args, **kwargs)
        if not published_failure:
            published_failure.append(True)
            raise OSError("synthetic restriction publication reply lost")
    value.store.restrictions._publish = publish_then_lose_reply
    record = CreateRecord("record.create", uuid4(), value.ids["class"], value.ids["term"],
        value.ids["student"], "ordinary_fact", now(), "synthetic browser retained fact", "")
    task = CreateTask("task.create", uuid4(), value.ids["class"], value.ids["term"],
        "synthetic browser retained task", None, value.ids["student"], record.record_id)
    for command in (record, task):
        proposal = value.worker.preview(*value.auth, command)
        value.worker.commit(*value.auth, proposal.proposal_id, uuid4())
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    app = create_durable_app(Settings(port=port), worker=value.worker, query=value.query, sdk=value.sdk)
    # Fixture clock, not an application endpoint or relaxed authentication.
    # Expire recent authentication after preview or after approval, exactly
    # once, so the real Gateway must refuse and the UI must permit recovery.
    @app.middleware("http")
    async def expire_recent_once(request, call_next):
        if request.url.path.endswith("/commands/" + reauth_phase) and not elapsed[0]:
            elapsed[0] = timedelta(minutes=6)
        return await call_next(request)
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / "apps/web/dist")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False,
        access_log=False, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(["node", "tests/durable-browser.mjs"], cwd=root / "apps/web",
            env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}", CLASS_OS_D1_REAUTH_PHASE=reauth_phase), capture_output=True,
            text=True, encoding="utf-8", timeout=130, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert published_failure == [True]
        with control[4].transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_run WHERE state='completed'")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE body IS NOT NULL")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM class_os.export_job")).scalar_one() == 1
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()


@pytest.mark.db
@pytest.mark.parametrize("fault", ["cancel", "timeout", "save", "claim", "audit"])
def test_actual_browser_never_releases_unsaved_or_replays_failed_run(control, monkeypatch, fault):
    calls = []
    async def respond(messages, info):
        calls.append(True)
        if fault in ("cancel", "timeout"):
            await asyncio.sleep(3)
        return ModelResponse(parts=[TextPart("synthetic unsaved failure answer must never display")])
    value = setup(control, respond=respond, timeout=.15 if fault == "timeout" else 10)
    started = time.monotonic()
    now = lambda: control[7][0] + timedelta(seconds=time.monotonic() - started)
    value.worker.clock = value.query.clock = value.worker.identity.clock = now
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic private failure canary")
    if fault == "save": monkeypatch.setattr(value.worker, "finish_result", fail)
    if fault == "claim": monkeypatch.setattr(value.worker, "claim", fail)
    if fault == "audit": monkeypatch.setattr(value.query, "agent_audit", fail)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    app = create_durable_app(Settings(port=port), worker=value.worker, query=value.query, sdk=value.sdk)
    mount_web(app, root / "apps/web/dist")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False,
        access_log=False, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(["node", "tests/durable-fault-browser.mjs"], cwd=root / "apps/web",
            env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}", CLASS_OS_D1_FAULT=fault),
            capture_output=True, text=True, encoding="utf-8", timeout=80,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert len(calls) == (0 if fault in ("claim", "audit") else 1)
        with control[4].transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_run")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE role='assistant'")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()
