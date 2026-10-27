"""Editable sourced summary against real QG/ISB/BCG/socket/PostgreSQL."""
from pathlib import Path
import os
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest
import uvicorn
from sqlalchemy import text

from class_os.domain.activity import CreateRecord, CreateTask
from class_os.interfaces.http.durable_conversation import create_durable_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_durable_conversation_http import setup
from test_conversation_control import control, storage, roster, identity


@pytest.mark.db
def test_actual_work_summary_edit_copy_offline_discard_has_no_business_write(control):
    value = setup(control)
    record = CreateRecord("record.create", uuid4(), value.ids["class"], value.ids["term"],
        value.ids["student"], "ordinary_fact", control[7][0], "synthetic summary fact", "synthetic summary observation")
    task = CreateTask("task.create", uuid4(), value.ids["class"], value.ids["term"],
        "synthetic summary task", None, value.ids["student"], record.record_id)
    for command in (record, task):
        proposal = value.worker.preview(*value.auth, command)
        value.worker.commit(*value.auth, proposal.proposal_id, uuid4())
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    app = create_durable_app(Settings(port=port), worker=value.worker, query=value.query, sdk=value.sdk)
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
        result = subprocess.run(["node", "tests/work-summary-browser.mjs"], cwd=root / "apps/web",
            env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}",
                CLASS_OS_TEST_CLASS=str(value.ids["class"]), CLASS_OS_TEST_TERM=str(value.ids["term"])), capture_output=True,
            text=True, encoding="utf-8", timeout=80, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        with control[4].transaction(read_only=True) as connection:
            # Only the deliberate independent BCG client adds a second task.
            for table, count in (("record_revision", 1), ("manual_task", 2), ("conversation_run", 0), ("export_job", 0)):
                assert connection.execute(text(f"SELECT count(*) FROM class_os.{table}")).scalar_one() == count
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()
