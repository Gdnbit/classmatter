from pathlib import Path
import json

import pytest

from portable_recovery import checked_path


def test_runtime_paths_stay_under_explicit_root(tmp_path: Path):
    assert checked_path(tmp_path, "primary-data") == (tmp_path / "primary-data").resolve()


@pytest.mark.parametrize("name", ["..", ".", "../outside"])
def test_runtime_path_escape_is_rejected(tmp_path: Path, name: str):
    with pytest.raises(RuntimeError):
        checked_path(tmp_path, name)


def test_tracked_live_evidence_proves_required_invariants():
    evidence_path = Path(__file__).parents[1] / "evidence" / "self-host-spike.latest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["postgres_version"] == "postgres (PostgreSQL) 18.6"
    assert evidence["synthetic_only"] is True
    assert evidence["restart_content_equal"] is True
    assert evidence["restore_content_equal"] is True
    assert evidence["outage_failed_closed"] is True
    assert evidence["business_commit_via_agent"] == 0
    assert evidence["task_row_count"] == 2


def test_compose_requires_external_password_and_binds_loopback():
    compose = (Path(__file__).parents[1] / "compose.yaml").read_text(encoding="utf-8")
    assert "CLASS_OS_POSTGRES_PASSWORD:?" in compose
    assert "127.0.0.1:" in compose
    password_line = next(line.strip() for line in compose.splitlines() if line.strip().startswith("POSTGRES_PASSWORD:"))
    assert password_line == "POSTGRES_PASSWORD: ${CLASS_OS_POSTGRES_PASSWORD:?set CLASS_OS_POSTGRES_PASSWORD outside Git}"
