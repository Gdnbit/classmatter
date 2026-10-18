"""Read-only metadata support, not log redaction or production ops evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from class_os.interfaces.operator.support import SupportReport, collect
from test_doctor import health_server, READY


def test_report_is_closed_metadata_and_does_not_read_runtime_or_forward_health_extras(monkeypatch):
    from class_os.interfaces.operator import support
    calls = []
    monkeypatch.setattr(support, "version", lambda name: calls.append(name) or "2.3.4")
    with health_server(body=json.dumps(READY).encode()) as (settings, requests):
        report = collect(settings)
    assert calls == ["class-os-backend", "pydantic-ai-slim", "openai", "pydantic", "fastapi"]
    assert requests == [("/health/live", None), ("/health/ready", None)]
    assert report.health.ready and not report.complete_support_bundle
    assert report.versions_scope == "operator-process-not-server"
    payload = report.model_dump(mode="json")
    assert SupportReport.model_validate(payload, strict=True) == report
    assert not any(payload[key] for key in ("business_data_collected", "secrets_collected", "logs_collected", "uploaded"))
    with pytest.raises(ValueError):
        SupportReport.model_validate({**payload, "environment": {"OPENAI_API_KEY": "synthetic-secret"}})
    for key in ("build_identity", "profile", "scope"):
        with pytest.raises(ValueError):
            SupportReport.model_validate({**payload, key: "untrusted-claim"})


@pytest.mark.parametrize("bad_version", ["3.8.0-secret-token", "C:/synthetic-secret/path", "1.2.3\nsecret", "9" * 10000, None], ids=["suffix", "path", "newline", "oversized", "not-string"])
def test_non_numeric_distribution_metadata_is_never_copied_to_support(monkeypatch, bad_version):
    from class_os.interfaces.operator import support
    monkeypatch.setattr(support, "version", lambda name: bad_version)
    with health_server(body=json.dumps(READY).encode()) as (settings, _):
        report = collect(settings)
    assert set(report.versions.model_dump().values()) >= {"unverified"}
    assert all(value == "unverified" for key, value in report.versions.model_dump().items() if key != "python")
    if type(bad_version) is str:
        assert json.dumps(bad_version) not in report.model_dump_json()


def test_health_response_and_exception_details_do_not_enter_report(monkeypatch):
    for body in ({**READY, "student_name": "SYNTHETIC-PRIVATE-NAME", "key": "SYNTHETIC-SECRET"},
                 {**READY, "components": {**READY["components"], "database": "SYNTHETIC-SECRET"}}):
        with health_server(body=json.dumps(body).encode()) as (settings, _):
            report = collect(settings)
        assert report.health.checks.ready == "invalid_response" and not report.health.ready
        assert "SYNTHETIC-" not in report.model_dump_json()
    from class_os.interfaces.operator import support
    monkeypatch.setattr(support, "diagnose", lambda settings: {"raw": "SYNTHETIC-SECRET"})
    with pytest.raises(ValueError):
        collect(settings)


@pytest.mark.parametrize("ready", [True, False])
def test_actual_cli_support_has_only_two_health_reads_no_cookie_proxy_redirect_or_secret(ready, tmp_path):
    body = READY if ready else {**READY, "status": "not_ready"}
    env = dict(os.environ, OPENAI_API_KEY="SYNTHETIC-ENV-SECRET", HTTP_PROXY="http://127.0.0.1:1",
               HTTPS_PROXY="http://127.0.0.1:1", ALL_PROXY="http://127.0.0.1:1")
    with health_server(200 if ready else 503, json.dumps(body).encode()) as (settings, requests):
        env.update(CLASS_OS_MODE="synthetic-development", CLASS_OS_HOST="127.0.0.1", CLASS_OS_MODEL_PROVIDER="fake", CLASS_OS_PORT=str(settings.port))
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "local.py"), "support"],
                                cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == (0 if ready else 1), result.stderr
    assert result.stderr == "" and "SYNTHETIC-ENV-SECRET" not in result.stdout
    report = SupportReport.model_validate_json(result.stdout)
    assert report.health.ready is ready
    assert requests == [("/health/live", None), ("/health/ready", None)]
    assert list(tmp_path.iterdir()) == []


def test_support_cli_never_instantiates_owned_runtime(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("support_local_cli", Path(__file__).resolve().parents[1] / "local.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    from class_os.infrastructure.local_runtime import LocalRuntime
    monkeypatch.setattr(LocalRuntime, "__init__", lambda *args: pytest.fail("No runtime credentials/configuration may be read"))
    with health_server(body=json.dumps(READY).encode()) as (settings, _):
        monkeypatch.setattr(sys, "argv", ["local.py", "support"])
        monkeypatch.setenv("CLASS_OS_PORT", str(settings.port))
        assert cli.main() == 0
    report = SupportReport.model_validate_json(capsys.readouterr().out)
    assert not report.secrets_collected and report.build_identity == "unverified"


def test_schema_snapshot_missing_package_and_incoherent_health_are_not_success(monkeypatch):
    from class_os.interfaces.operator import support
    from importlib.metadata import PackageNotFoundError
    snapshot = Path(__file__).resolve().parents[2] / "contracts/operator/support.v1.schema.json"
    assert json.loads(snapshot.read_text(encoding="utf-8")) == SupportReport.model_json_schema()
    def missing(name):
        raise PackageNotFoundError(name)
    monkeypatch.setattr(support, "version", missing)
    with health_server(body=json.dumps(READY).encode()) as (settings, _):
        report = collect(settings)
    assert report.versions.backend == report.versions.pydantic_ai == report.versions.openai == "unavailable"
    payload = report.model_dump(mode="json")
    assert len(report.model_dump_json().encode()) < 4096
    with pytest.raises(ValueError):
        SupportReport.model_validate({**payload, "health": {**payload["health"], "ready": False}}, strict=True)
    with pytest.raises(ValueError):
        SupportReport.model_validate({**payload, "health": {**payload["health"], "checks": {**payload["health"]["checks"], "unknown": "SYNTHETIC-PRIVATE"}}}, strict=True)


def test_redirect_health_does_not_follow_or_copy_body_into_report():
    with health_server(302, b"SYNTHETIC-SECRET", redirect=True) as (settings, requests):
        report = collect(settings)
    assert report.health.checks.ready == "invalid_response" and not report.health.ready
    assert requests == [("/health/live", None), ("/health/ready", None)]
    assert "SYNTHETIC-SECRET" not in report.model_dump_json()
