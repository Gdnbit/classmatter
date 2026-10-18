import httpx
import pytest
from sqlalchemy import text

from class_os.infrastructure.local_runtime import compose
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.interfaces.http.settings import Settings


@pytest.mark.db
@pytest.mark.asyncio
async def test_missing_required_feature_permission_cannot_report_ready(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)
    class FixtureRuntime:
        def database(self, role):
            return Database(database_urls[role], identity=role == "identity")
    app = compose(Settings(), FixtureRuntime())
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
            assert (await client.get("/health/ready")).status_code == 200
            for column in ("name", "start_date", "end_date"):
                with owner.transaction() as connection:
                    # The finite, test-owned list above is not a user SQL input.
                    connection.execute(text(f"REVOKE UPDATE({column}) ON class_os.academic_term FROM class_os_runtime"))
                assert (await client.get("/health/ready")).status_code == 503
                with owner.transaction() as connection:
                    connection.execute(text(f"GRANT UPDATE({column}) ON class_os.academic_term TO class_os_runtime"))
                assert (await client.get("/health/ready")).status_code == 200
            with owner.transaction() as connection:
                connection.execute(text("UPDATE class_os.alembic_version SET version_num='0009'"))
            assert (await client.get("/health/ready")).status_code == 503
            with owner.transaction() as connection:
                connection.execute(text("UPDATE class_os.alembic_version SET version_num='0016'"))
            assert (await client.get("/health/ready")).status_code == 200
            with owner.transaction() as connection:
                connection.execute(text("REVOKE UPDATE(name) ON class_os.student FROM class_os_runtime"))
            assert (await client.get("/health/ready")).status_code == 503
            with owner.transaction() as connection:
                connection.execute(text("GRANT UPDATE(name) ON class_os.student TO class_os_runtime"))
            assert (await client.get("/health/ready")).status_code == 200
            with owner.transaction() as connection:
                connection.execute(text("REVOKE UPDATE(title,due_at) ON class_os.manual_task FROM class_os_runtime"))
            assert (await client.get("/health/ready")).status_code == 503
            with owner.transaction() as connection:
                connection.execute(text("GRANT UPDATE(title,due_at) ON class_os.manual_task TO class_os_runtime"))
            assert (await client.get("/health/ready")).status_code == 200
            with owner.transaction() as connection:
                connection.execute(text("REVOKE UPDATE(valid_to) ON class_os.student_identifier FROM class_os_runtime"))
            unready = await client.get("/health/ready")
            assert unready.status_code == 503
            assert set(unready.json()["components"].values()) == {"unverified"}
            with owner.transaction() as connection:
                connection.execute(text("GRANT UPDATE(valid_to) ON class_os.student_identifier TO class_os_runtime"))
            assert (await client.get("/health/ready")).status_code == 200
    finally:
        owner.close()
