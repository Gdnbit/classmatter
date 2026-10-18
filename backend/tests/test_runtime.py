"""Real loopback server lifecycle and composition boundaries."""
import ast
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]


def test_real_tcp_start_health_and_shutdown():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, CLASS_OS_PORT=str(port), CLASS_OS_MODE="synthetic-development",
               CLASS_OS_HOST="127.0.0.1", CLASS_OS_MODEL_PROVIDER="fake")
    # Pipes are not used: bounded test cannot hang on a filled log buffer.
    process = subprocess.Popen([sys.executable, str(ROOT / "serve.py")], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False) as client:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, "Backend exited before startup"
                try:
                    live = client.get("/health/live")
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    assert time.monotonic() < deadline, "Backend startup timed out"
                    time.sleep(0.05)
            assert live.status_code == 200
            assert live.json()["status"] == "alive"
            assert client.get("/health/ready").status_code == 503
            assert client.get("/health/live", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
            assert client.post("/business-command").status_code == 404
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    assert process.poll() is not None


def test_launcher_rejects_public_binding_without_listener():
    env = dict(os.environ, CLASS_OS_HOST="0.0.0.0")
    result = subprocess.run([sys.executable, str(ROOT / "serve.py")], env=env,
                            capture_output=True, text=True, timeout=10,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode != 0
    assert "Invalid backend settings" in result.stderr


def test_composition_does_not_import_business_storage_or_spikes():
    banned = {"psycopg", "sqlalchemy", "sqlite3", "pydantic_ai", "spikes", "scripts"}
    for source in (ROOT / "src/class_os/interfaces").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            assert not banned.intersection(name.split(".")[0] for name in imports), source


def test_domain_and_application_are_independent_of_transport_and_database():
    banned = {"fastapi", "starlette", "sqlalchemy", "psycopg", "pwdlib", "pydantic_ai", "spikes"}
    for layer in ("domain", "application"):
        for source in (ROOT / "src/class_os" / layer).rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or ""]
                else:
                    continue
                assert not banned.intersection(name.split(".")[0] for name in imports), source
