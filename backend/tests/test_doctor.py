from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread

import pytest

from class_os.interfaces.http.settings import Settings
from class_os.interfaces.operator.doctor import diagnose


LIVE = {"schema_version": "class-os.health.v1", "service": "class-os-api", "mode": "synthetic-development", "status": "alive"}
READY = {**LIVE, "status": "ready", "components": {"database": "connected", "identity": "connected", "business_gateways": "connected"}}


@contextmanager
def health_server(status=200, body=None, *, redirect=False, live_body=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("Cookie")))
            if self.path == "/health/live":
                code, raw = 200, live_body if live_body is not None else json.dumps(LIVE).encode()
            else:
                code, raw = status, body if body is not None else json.dumps(READY).encode()
            self.send_response(code)
            if redirect and self.path == "/health/ready":
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/must-not-follow")
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Settings(port=server.server_port), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_doctor_real_tcp_ready_and_no_cookie_or_business_request():
    with health_server() as (settings, requests):
        result = diagnose(settings)
    assert result["ready"] is True and result["complete_operator_check"] is False
    assert requests == [("/health/live", None), ("/health/ready", None)]


def test_doctor_old_health_only_503_is_not_ready():
    body = {**READY, "status": "not_ready", "components": {"database": "not_configured", "identity": "not_configured", "business_gateways": "not_configured"}}
    with health_server(503, json.dumps(body).encode()) as (settings, _):
        result = diagnose(settings)
    assert result["checks"]["ready"] == "not_ready" and not result["ready"]


def test_doctor_does_not_fill_missing_live_evidence_with_model_defaults():
    with health_server(live_body=b"{}") as (settings, _):
        result = diagnose(settings)
    assert result["checks"]["live"] == "invalid_response" and not result["ready"]


@pytest.mark.parametrize("status,body", [(500, b"private synthetic exception detail"), (200, b"{}"), (200, b"x" * 8193),
                                       (200, json.dumps({**READY, "secret": "must-not-echo"}).encode()),
                                       (200, b'{"status":"ready","status":"not_ready"}'),
                                       (200, ("[" * 1100 + "]" * 1100).encode())])
def test_doctor_invalid_responses_never_become_ready_or_echo_body(status, body):
    with health_server(status, body) as (settings, _):
        result = diagnose(settings)
    assert result["checks"]["ready"] == "invalid_response" and not result["ready"]
    assert "must-not-echo" not in json.dumps(result) and "private synthetic" not in json.dumps(result)


def test_doctor_does_not_follow_redirect():
    with health_server(302, b"", redirect=True) as (settings, requests):
        result = diagnose(settings)
    assert result["checks"]["ready"] == "invalid_response"
    assert all(path != "/must-not-follow" for path, _ in requests)


def test_doctor_stopped_owned_server_is_unavailable():
    with health_server() as (settings, _):
        pass
    result = diagnose(settings)
    assert not result["ready"] and set(result["checks"].values()) == {"unavailable"}
    assert result["next_step"] == "start-local-api"


@pytest.mark.parametrize("ready", [True, False])
def test_actual_operator_cli_json_and_exit_status_without_runtime_configuration(ready):
    body = READY if ready else {**READY, "status": "not_ready"}
    with health_server(200 if ready else 503, json.dumps(body).encode()) as (settings, _):
        result = subprocess.run([sys.executable, "local.py", "doctor"], cwd=Path(__file__).resolve().parents[1],
                                env=dict(os.environ, CLASS_OS_MODE="synthetic-development", CLASS_OS_HOST="127.0.0.1",
                                         CLASS_OS_MODEL_PROVIDER="fake", CLASS_OS_PORT=str(settings.port)),
                                capture_output=True, text=True, encoding="utf-8", timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == (0 if ready else 1), result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is ready and output["complete_operator_check"] is False


def test_operator_module_does_not_import_database_or_model_runtime():
    probe = (
        "import runpy,sys; runpy.run_path('local.py', run_name='operator_import_probe'); "
        "assert 'class_os.infrastructure.local_runtime' not in sys.modules; "
        "assert 'pydantic_ai' not in sys.modules; assert 'openai' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding="utf-8", timeout=10,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr
