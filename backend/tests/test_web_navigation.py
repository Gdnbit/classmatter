"""Closed UI shell routes are not an API query/authentication bypass."""
from pathlib import Path
import socket
import subprocess
import threading
import time
from datetime import timedelta
import os

from fastapi.testclient import TestClient
import httpx
import pytest
import uvicorn
from sqlalchemy import text

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_roster_gateway import roster
from test_identity import identity


def test_closed_web_paths_and_queries_do_not_relax_api_boundary(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>synthetic-shell</html>", encoding="utf-8")
    app = create_app(Settings())
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 12)) as client:
        assert client.get("/students?view=table").status_code == 400  # Not mounted.
        mount_web(app, tmp_path)
        for path in ("/students?view=table", "/students/00000000-0000-0000-0000-000000000001?tab=tasks", "/work?filter=waiting", "/settings/user", "/data/spreadsheets/score-001"):
            response = client.get(path)
            assert response.status_code == 200 and "synthetic-shell" in response.text
            assert response.headers["cache-control"] == "no-store"
        for path in ("/api/not-real?view=table", "/health/live?view=table", "/assets/x?view=table", "/students?view=table&view=list", "/work?student=not-a-uuid", "/work?filter=unknown", "/students?name=synthetic-private-name", "/students?view=", "/work?" + "x" * 513):
            response = client.get(path)
            assert response.status_code == 400
            assert "synthetic-private" not in response.text and "synthetic-shell" not in response.text
        assert client.post("/students?view=table").status_code == 400
        for path in ("/api/not-real", "/not-a-page", "/assets/not-real.js", "/backend/README.md"):
            response = client.get(path)
            assert response.status_code == 404 and "synthetic-shell" not in response.text


@pytest.mark.db
def test_real_browser_navigation_and_single_world_views(roster):
    business, query, _, _, boundary, owner, clock = roster
    started = time.monotonic()
    def now():
        return clock[0] + timedelta(seconds=time.monotonic() - started)
    business.clock = query.clock = boundary.clock = now
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    # No Agent/Provider adapter is installed: direct UI must be sufficient.
    app = create_app(Settings(port=port), identity=boundary, business=business, query=query)
    mount_web(app, root / "apps/web/dist")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="error", proxy_headers=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        with httpx.Client(trust_env=False) as client:
            assert client.get(f"http://127.0.0.1:{port}/students?view=table").status_code == 200
        result = subprocess.run(["node", "tests/runtime-navigation-browser.mjs"], cwd=root / "apps/web",
                                env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}"), timeout=100,
                                capture_output=True, text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.student")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 2
            assert connection.execute(text("SELECT count(DISTINCT record_id) FROM class_os.record_revision")).scalar_one() == 1
            assert connection.execute(text("SELECT title, status, version FROM class_os.manual_task")).one() == ("合成导航跟进已更正", "waiting", 3)
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        assert not thread.is_alive()
