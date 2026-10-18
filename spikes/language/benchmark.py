from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
PYTHON_ROOT = SPIKE_ROOT / "python"
TYPESCRIPT_ROOT = SPIKE_ROOT / "typescript"
FIXTURE = json.loads(
    (ROOT / "evals/class-os-v1/fixtures/r1/canonical-r1.synthetic.json").read_text(encoding="utf-8")
)


@dataclass(frozen=True)
class Candidate:
    name: str
    command: tuple[str, ...]
    cwd: Path
    port: int
    source_files: tuple[Path, ...]
    direct_dependency_count: int
    locked_dependency_count: int


def _request(url: str, payload: dict[str, Any] | None = None, timeout: float = 2.0) -> tuple[int, bytes]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _start(candidate: Candidate) -> tuple[subprocess.Popen[bytes], float]:
    env = os.environ.copy()
    env["PORT"] = str(candidate.port)
    started = time.perf_counter()
    process = subprocess.Popen(
        candidate.command,
        cwd=candidate.cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise RuntimeError(
                f"{candidate.name} exited before health check: "
                f"stdout={stdout.decode(errors='replace')} stderr={stderr.decode(errors='replace')}"
            )
        try:
            status, _ = _request(f"http://127.0.0.1:{candidate.port}/health", timeout=0.25)
            if status == 200:
                return process, (time.perf_counter() - started) * 1000
        except (OSError, TimeoutError):
            pass
        time.sleep(0.01)
    _stop(process)
    raise RuntimeError(f"{candidate.name} did not become healthy within 15 seconds")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _source_loc(paths: tuple[Path, ...]) -> int:
    count = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "//")):
                count += 1
    return count


def _process_tree_rss_mb(process_id: int) -> float:
    root = psutil.Process(process_id)
    processes = [root, *root.children(recursive=True)]
    return sum(process.memory_info().rss for process in processes if process.is_running()) / (1024 * 1024)


def _pnpm_locked_dependency_count(path: Path) -> int:
    in_packages = False
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "packages:":
            in_packages = True
            continue
        if line == "snapshots:":
            break
        if in_packages and re.match(r"^  \S.*:$", line):
            count += 1
    return count


def benchmark(candidate: Candidate, cold_runs: int, requests: int) -> tuple[dict[str, Any], dict[str, Any]]:
    startup_ms: list[float] = []
    rss_mb: list[float] = []
    for _ in range(cold_runs):
        process, elapsed = _start(candidate)
        try:
            startup_ms.append(elapsed)
            rss_mb.append(_process_tree_rss_mb(process.pid))
        finally:
            _stop(process)

    process, _ = _start(candidate)
    try:
        payload = {"workspace_id": FIXTURE["workspace_a"]["workspace_id"], "limit": 20}
        url = f"http://127.0.0.1:{candidate.port}/v1/attention/list"
        for _ in range(20):
            status, response = _request(url, payload)
            if status != 200:
                raise RuntimeError(f"{candidate.name} warmup returned {status}: {response!r}")
        latencies: list[float] = []
        canonical_response: dict[str, Any] | None = None
        for _ in range(requests):
            started = time.perf_counter()
            status, response = _request(url, payload)
            latencies.append((time.perf_counter() - started) * 1000)
            if status != 200:
                raise RuntimeError(f"{candidate.name} request returned {status}: {response!r}")
            parsed = json.loads(response)
            if canonical_response is None:
                canonical_response = parsed
            elif parsed != canonical_response:
                raise RuntimeError(f"{candidate.name} returned nondeterministic response")
    finally:
        _stop(process)

    assert canonical_response is not None
    measurement = {
        "cold_start_ms_median": round(statistics.median(startup_ms), 3),
        "cold_start_ms_runs": [round(value, 3) for value in startup_ms],
        "rss_mb_median": round(statistics.median(rss_mb), 3),
        "rss_mb_runs": [round(value, 3) for value in rss_mb],
        "request_count": requests,
        "latency_ms_p50": round(_percentile(latencies, 0.50), 3),
        "latency_ms_p95": round(_percentile(latencies, 0.95), 3),
        "source_loc": _source_loc(candidate.source_files),
        "direct_dependency_count": candidate.direct_dependency_count,
        "locked_dependency_count": candidate.locked_dependency_count,
    }
    return measurement, canonical_response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cold-runs", type=int, default=5)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument(
        "--output", type=Path, default=SPIKE_ROOT / "evidence/language-spike.latest.json"
    )
    args = parser.parse_args()
    python_executable = PYTHON_ROOT / ".venv/Scripts/python.exe"
    candidates = (
        Candidate(
            name="python-fastapi",
            command=(str(python_executable), "app.py"),
            cwd=PYTHON_ROOT,
            port=8761,
            source_files=(PYTHON_ROOT / "app.py", PYTHON_ROOT / "test_app.py"),
            direct_dependency_count=3,
            locked_dependency_count=(PYTHON_ROOT / "uv.lock").read_text(encoding="utf-8").count("[[package]]"),
        ),
        Candidate(
            name="typescript-fastify",
            command=("node", "server.mjs"),
            cwd=TYPESCRIPT_ROOT,
            port=8762,
            source_files=(TYPESCRIPT_ROOT / "server.mjs", TYPESCRIPT_ROOT / "server.test.mjs"),
            direct_dependency_count=2,
            locked_dependency_count=_pnpm_locked_dependency_count(TYPESCRIPT_ROOT / "pnpm-lock.yaml"),
        ),
    )
    measurements: dict[str, Any] = {}
    responses: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        measurements[candidate.name], responses[candidate.name] = benchmark(
            candidate, args.cold_runs, args.requests
        )
    if responses[candidates[0].name] != responses[candidates[1].name]:
        raise RuntimeError("candidates produced different response contracts")
    response_bytes = json.dumps(
        responses[candidates[0].name], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    evidence = {
        "schema": "class-os.language-spike-evidence/v1",
        "observed_at": datetime.now().astimezone().isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "processor": platform.processor(),
        },
        "fixture_seed": FIXTURE["meta"]["seed"],
        "contract_response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "contract_responses_equal": True,
        "measurements": measurements,
        "limitations": [
            "Synthetic read-only endpoint; no database, TLS, auth, audit store, Agent model or concurrent load.",
            "Single Windows host observation; numbers compare candidates here and are not production capacity promises.",
            "RSS is the server process-tree working set after health; shared/runtime pages are not normalized.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
