"""Owned PG DDL, explicit D1 opt-in, no implicit default R1 upgrade."""
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from class_os.domain.conversation_results import RESULT_COLUMNS
from class_os.domain.exit_package import checksum
from class_os.infrastructure.persistence.schema_inventory import schema_profile, validate_surface
from class_os.infrastructure.persistence.database import Database
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from test_activity_gateway import seed
from test_durable_conversation_storage import storage, roster, identity, thread, turn, queued, message


@pytest.mark.db
def test_actual_nonempty_0025_to_0026_upgrade_preserves_legacy_rows(roster, database_urls):
    classroom, student, _ = seed(roster)
    auth = roster[4].authenticate(*roster[3][:3])
    owner = Database(database_urls["migrator"], migration=True, profile="conversation-d1")
    try:
        with owner.transaction() as connection:
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "db/migrations"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0025")
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0025"
            enrollment = connection.execute(text("SELECT enrollment_id FROM class_os.enrollment WHERE student_id=:student"), {"student": student.student_id}).scalar_one()
            values = {"workspace": auth.workspace_id, "owner": auth.owner_id, "class": classroom.class_id,
                "term": classroom.term_id, "student": student.student_id, "enrollment": enrollment,
                "at": roster[6][0], "thread": uuid4(), "turn": uuid4(), "run": uuid4(), "key": uuid4()}
            thread(connection, values)
            turn(connection, values)
            queued(connection, values)
            message(connection, values)
            tables = ("conversation_thread", "conversation_turn", "conversation_run", "conversation_message")
            before = {table: connection.execute(text("SELECT jsonb_agg(to_jsonb(r)) FROM class_os." + table + " r")).scalar_one() for table in tables}
            command.upgrade(config, "0026")
            assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0026"
            after = {table: connection.execute(text("SELECT jsonb_agg(to_jsonb(r)) FROM class_os." + table + " r")).scalar_one() for table in tables}
            assert before == after
            validate_surface(connection, complete=True, profile="conversation-d1")
            validate_role_guards(connection, profile="conversation-d1")
            for table in RESULT_COLUMNS:
                assert connection.execute(text("SELECT count(*) FROM class_os." + table)).scalar_one() == 0
    finally:
        owner.close()


def upgraded(storage):
    owner, runtime, private, values = storage
    with owner.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        message(connection, values)
        message(connection, values, role="assistant", origin="assistant-unverified", body="synthetic old reply")
        connection.execute(text("""UPDATE class_os.conversation_run SET state='completed',version=3,
            generation=:generation,started_at=:at,lease_until=:at+interval '1 minute',ended_at=:at"""),
            {**values, "generation": uuid4()})
        before = connection.execute(text("SELECT jsonb_agg(to_jsonb(m) ORDER BY role) FROM class_os.conversation_message m")).scalar_one()
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "db/migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "0026")
        assert connection.execute(text("SELECT jsonb_agg(to_jsonb(m) ORDER BY role) FROM class_os.conversation_message m")).scalar_one() == before
        assistant = connection.execute(text("SELECT message_id FROM class_os.conversation_message WHERE role='assistant'")).scalar_one()
        user = connection.execute(text("SELECT message_id FROM class_os.conversation_message WHERE role='user'")).scalar_one()
    return owner, runtime, private, {**values, "assistant": assistant, "user": user, "source": uuid4(), "receipt": uuid4(), "draft": uuid4()}


SOURCE = """INSERT INTO class_os.conversation_query_source
    (workspace_id,thread_id,turn_id,message_id,source_id,ordinal,source_workspace_id,source_owner_id,receipt_id,projection_hash,as_of,created_at)
    VALUES(:workspace,:thread,:turn,:assistant,:source,:ordinal,:workspace,:owner,:receipt,:hash,:at,:at)"""
DRAFT = """INSERT INTO class_os.conversation_task_draft
    (workspace_id,thread_id,turn_id,message_id,draft_id,title,title_hash,visibility,created_at)
    VALUES(:workspace,:thread,:turn,:assistant,:draft,'synthetic candidate',:title_hash,'visible',:at)"""


@pytest.mark.db
def test_result_tables_preserve_old_rows_and_default_r1_still_refuses(storage):
    owner, runtime, private, values = upgraded(storage)
    assert schema_profile()[0] == "0016" and schema_profile("conversation-d1")[0] == "0026"
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0026"
        for table, columns in RESULT_COLUMNS.items():
            assert set(connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='class_os' AND table_name=:t"), {"t": table}).scalars()) == set(columns)
            assert connection.execute(text("SELECT count(*) FROM class_os." + table)).scalar_one() == 0
        with pytest.raises(RuntimeError, match="Unregistered"):
            validate_surface(connection, complete=True, profile="r1")
    with runtime.transaction() as connection:
        connection.execute(text(SOURCE), {**values, "ordinal": 1, "hash": "a" * 64})
        connection.execute(text(DRAFT), {**values, "title_hash": checksum("synthetic candidate")})
    for database, statement in ((private, "SELECT * FROM class_os.conversation_query_source"),
            (runtime, "UPDATE class_os.conversation_query_source SET ordinal=ordinal"),
            (runtime, "UPDATE class_os.conversation_task_draft SET title_hash=title_hash"),
            (runtime, "DELETE FROM class_os.conversation_task_draft")):
        with pytest.raises(ProgrammingError):
            with database.transaction() as connection:
                connection.execute(text(statement))


@pytest.mark.db
@pytest.mark.parametrize("fault", ["user-message", "other-turn", "ordinal", "duplicate-source", "duplicate-draft"])
def test_full_assistant_scope_and_result_bounds_are_enforced_in_pg(storage, fault):
    _, runtime, _, values = upgraded(storage)
    args = {**values, "ordinal": 1, "hash": "a" * 64, "title_hash": checksum("synthetic candidate")}
    if fault == "user-message":
        args["assistant"] = args["user"]
    elif fault == "other-turn":
        args["turn"] = uuid4()
    elif fault == "ordinal":
        args["ordinal"] = 3
    elif fault == "duplicate-source":
        with runtime.transaction() as connection:
            connection.execute(text(SOURCE), args)
        args.update(source=uuid4(), ordinal=2)
    else:
        with runtime.transaction() as connection:
            connection.execute(text(DRAFT), args)
        args["draft"] = uuid4()
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            connection.execute(text(DRAFT if fault == "duplicate-draft" else SOURCE), args)
