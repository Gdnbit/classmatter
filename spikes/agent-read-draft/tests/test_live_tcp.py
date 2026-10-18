"""Own and stop a disposable server; never claim UI validation from this test."""
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def test_real_tcp_stream_and_abort():
    root = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    assert node, "Node >=22.12 is required for the browser transport spike"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen([sys.executable, "browser_fixture.py", "--port", str(port)],
                               cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ready = False
        for _ in range(100):
            assert process.poll() is None, "fixture exited before startup"
            try:
                with urllib.request.urlopen(f"{origin}/spike", timeout=0.2) as response:
                    ready = response.status == 200
                if ready:
                    break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)
        assert ready, "fixture startup timed out"
        completed = subprocess.run([node, "--test", "network.test.mjs"], cwd=root / "browser",
                                   env={**os.environ, "CLASS_OS_SPIKE_ORIGIN": origin},
                                   capture_output=True, text=True, encoding="utf-8", timeout=15)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
