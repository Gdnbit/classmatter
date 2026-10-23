"""Server-time overdue projections refresh without business writes or a model."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from datetime import timedelta
from uuid import uuid4

import pytest
import uvicorn
from sqlalchemy import text

from class_os.domain.activity import CreateTask
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.db
def test_real_deadlines_refresh_server_projection_without_business_mutation(roster):
    business, query, _, credentials, boundary, owner, clock = roster
    classroom, student, _ = seed(roster)
    for index, seconds in enumerate((12, 28, 44), 1):
        submit(business, credentials, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
               f"合成到期核对{index}", clock[0] + timedelta(seconds=seconds), student.student_id, None))
    started = time.monotonic()
    def now():
        return clock[0] + timedelta(seconds=time.monotonic() - started)
    business.clock = query.clock = boundary.clock = now
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    app = create_app(Settings(port=port), identity=boundary, business=business, query=query)
    mount_web(app, root / "apps/web/dist")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(["node", "tests/runtime-deadline-browser.mjs"], cwd=root / "apps/web",
                    env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}"), timeout=90,
                    capture_output=True, text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.manual_task WHERE version=1 AND status='not-started'")).scalar_one() == 3
            assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 3
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        assert not thread.is_alive()
