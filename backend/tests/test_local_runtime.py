"""Runtime composition and Windows protected-secret smoke, no real records."""
import os
from pathlib import Path
import secrets

import httpx
import pytest

from class_os.infrastructure.local_runtime import LocalRuntime, ROOT, compose, protect
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.interfaces.http.settings import Settings


def test_runtime_root_is_ignored_repository_local_not_parent():
    assert ROOT == Path(__file__).resolve().parents[2] / ".local-runtime/synthetic-v1"


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI profile")
def test_current_user_dpapi_roundtrip_and_no_plaintext():
    value = secrets.token_bytes(48)
    protected = protect(value)
    assert value not in protected
    assert protect(protected, decrypt=True) == value
    with pytest.raises(RuntimeError):
        protect(b"invalid", decrypt=True)


@pytest.mark.db
@pytest.mark.asyncio
async def test_supported_composition_ready_and_database_failure(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)

    class FixtureRuntime:
        def database(self, role):
            assert role in {"identity", "runtime"}
            return Database(database_urls[role], identity=role == "identity")

    app = compose(Settings(), FixtureRuntime())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        assert (await client.get("/health/ready")).status_code == 200
        assert (await client.get("/api/identity/context")).status_code == 200
        assert (await client.get("/api/identity/session")).status_code == 401
    owner.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Windows operator profile")
@pytest.mark.parametrize("directory", ["owned-runtime", "合成运行目录"])
def test_owned_runtime_restart_with_scram_and_no_plaintext(tmp_path, request, directory):
    runtime = LocalRuntime(tmp_path / directory)
    runtime.initialize(request.config.getoption("--pg-root"))
    config = runtime.configuration()
    assert "trust" not in (runtime.cluster / "pg_hba.conf").read_text(encoding="utf-8")
    assert set(config) == {"profile", "pg_bin", "port", "database"}
    with pytest.raises(RuntimeError):
        runtime.initialize(request.config.getoption("--pg-root"))
    runtime.start()
    try:
        db = runtime.database("runtime")
        with db.transaction(read_only=True) as connection:
            from sqlalchemy import text
            assert connection.execute(text("SELECT data_mode FROM class_os.database_state")).scalar_one() == "synthetic-only"
        db.close()
    finally:
        runtime.stop()
