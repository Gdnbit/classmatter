"""D1 schema foundation on disposable PG; not an application write pathway."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import REGISTERED_TABLES, D1_TABLES, validate_surface, schema_profile
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from test_activity_gateway import roster, identity, seed
from class_os.infrastructure.exit_package import ExitTransaction
from class_os.infrastructure.operator_backup import SyntheticBackup


@pytest.fixture
def storage(roster, database_urls):
    classroom, student, _ = seed(roster)
    owner = Database(database_urls["migrator"], migration=True, profile="conversation-d1")
    runtime = Database(database_urls["runtime"], profile="conversation-d1")
    private = Database(database_urls["identity"], identity=True, profile="conversation-d1")
    migrate(owner)
    boundary = roster[4]
    auth = boundary.authenticate(*roster[3][:3])
    with owner.transaction(read_only=True) as connection:
        enrollment = connection.execute(text("SELECT enrollment_id FROM class_os.enrollment WHERE student_id=:student"),
                                        {"student": student.student_id}).scalar_one()
    values = {"workspace": auth.workspace_id, "owner": auth.owner_id, "class": classroom.class_id,
              "term": classroom.term_id, "student": student.student_id, "enrollment": enrollment,
              "at": roster[6][0], "thread": uuid4(), "turn": uuid4(), "run": uuid4(), "key": uuid4()}
    try:
        yield owner, runtime, private, values
    finally:
        owner.close()
        runtime.close()
        private.close()


def thread(connection, values):
    connection.execute(text("""INSERT INTO class_os.conversation_thread
        (workspace_id,thread_id,owner_id,class_id,term_id,student_id,enrollment_id,title,status,version,created_at,updated_at)
        VALUES(:workspace,:thread,:owner,:class,:term,:student,:enrollment,'合成班务对话','active',1,:at,:at)"""), values)


def turn(connection, values, ordinal=1):
    connection.execute(text("""INSERT INTO class_os.conversation_turn
        (workspace_id,thread_id,turn_id,ordinal,client_request_id,request_hash,mode,draft_kind,created_at)
        VALUES(:workspace,:thread,:turn,:ordinal,:key,:hash,'read','task',:at)"""),
        {**values, "ordinal": ordinal, "hash": "a" * 64})


def queued(connection, values):
    connection.execute(text("""INSERT INTO class_os.conversation_run
        (workspace_id,thread_id,turn_id,run_id,state,version,created_at,queued_until)
        VALUES(:workspace,:thread,:turn,:run,'queued',1,:at,:at+interval '1 minute')"""), values)


def message(connection, values, *, body="合成原文", role="user", origin="user-original", visibility="visible"):
    connection.execute(text("""INSERT INTO class_os.conversation_message
        (workspace_id,thread_id,turn_id,message_id,role,origin,visibility,body,created_at)
        VALUES(:workspace,:thread,:turn,:message,:role,:origin,:visibility,:body,:at)"""),
        {**values, "message": uuid4(), "role": role, "origin": origin, "body": body, "visibility": visibility})


def test_profile_is_closed_without_database_or_model_discovery():
    assert schema_profile() == ("0016", REGISTERED_TABLES)
    assert schema_profile("conversation-d1") == ("0018", REGISTERED_TABLES | D1_TABLES)
    for profile in (None, {}, "head", "d1", "r1 "):
        with pytest.raises(ValueError, match="schema profile"):
            schema_profile(profile)
        with pytest.raises(ValueError, match="schema profile"):
            Database("not-a-url", profile=profile)


@pytest.mark.db
def test_nonempty_r1_upgrade_is_explicit_idempotent_and_not_default_admitted(storage, database_urls):
    owner, runtime, private, values = storage
    migrate(owner)
    with owner.transaction(read_only=True) as connection:
        assert validate_surface(connection, complete=True, profile="conversation-d1") == REGISTERED_TABLES | D1_TABLES
        assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0018"
        assert connection.execute(text("SELECT count(*) FROM class_os.student WHERE student_id=:student"), values).scalar_one() == 1
        validate_role_guards(connection, profile="conversation-d1")
        with pytest.raises(RuntimeError, match="Unregistered"):
            validate_surface(connection, complete=True)
    old = Database(database_urls["migrator"], migration=True)
    try:
        with pytest.raises(RuntimeError, match="Unregistered"):
            migrate(old)
    finally:
        old.close()
    with pytest.raises(PermissionError):
        migrate(runtime)
    with pytest.raises(PermissionError):
        migrate(private)


@pytest.mark.db
def test_runtime_scope_immutable_columns_and_identity_separation(storage):
    owner, runtime, private, values = storage
    with runtime.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        message(connection, values)
    for statement in ("UPDATE class_os.conversation_thread SET owner_id=owner_id",
                      "UPDATE class_os.conversation_turn SET request_hash=request_hash",
                      "UPDATE class_os.conversation_message SET origin=origin",
                      "UPDATE class_os.conversation_run SET turn_id=turn_id",
                      "DELETE FROM class_os.conversation_message", "TRUNCATE class_os.conversation_run",
                      "CREATE TABLE class_os.d1_unregistered(x int)"):
        with pytest.raises(ProgrammingError):
            with runtime.transaction() as connection:
                connection.execute(text(statement))
    with pytest.raises(ProgrammingError):
        with private.transaction(read_only=True) as connection:
            connection.execute(text("SELECT * FROM class_os.conversation_message"))
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT body FROM class_os.conversation_message")).scalar_one() == "合成原文"


@pytest.mark.db
@pytest.mark.parametrize("field", ["workspace", "owner", "class", "term", "student", "enrollment"])
def test_thread_cannot_splice_other_scope_or_nonexistent_membership(storage, field):
    _, runtime, _, values = storage
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            thread(connection, {**values, field: uuid4()})


@pytest.mark.db
def test_key_payload_coordinate_ordinal_and_active_slot_are_unique(storage):
    _, runtime, _, values = storage
    with runtime.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
    # Neither a changed hash nor new IDs make the same request key reusable.
    for changed, ordinal in (({"turn": uuid4()}, 2), ({"turn": uuid4(), "key": uuid4()}, 1)):
        with pytest.raises(IntegrityError):
            with runtime.transaction() as connection:
                turn(connection, {**values, **changed}, ordinal)
    second = {**values, "turn": uuid4(), "key": uuid4(), "run": uuid4()}
    with runtime.transaction() as connection:
        turn(connection, second, 2)
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            queued(connection, second)
    # Expired clock alone never releases the partial unique slot.
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            queued(connection, {**second, "at": values["at"] + timedelta(minutes=2)})
    with runtime.transaction() as connection:
        connection.execute(text("""UPDATE class_os.conversation_run SET state='cancelled',version=2,ended_at=:at
            WHERE run_id=:run"""), values)
        queued(connection, second)


@pytest.mark.db
@pytest.mark.parametrize("kwargs", [{"role": "assistant", "origin": "fact"}, {"role": "system"},
    {"body": "x" * 2001}, {"body": "合" * 5334, "role": "assistant", "origin": "assistant-unverified"},
    {"body": "retained", "visibility": "restricted"}, {"body": None}, {"body": ""}, {"body": "\n\t "}])
def test_messages_reject_invalid_authority_size_and_restricted_body(storage, kwargs):
    _, runtime, _, values = storage
    with runtime.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            message(connection, values, **kwargs)


@pytest.mark.db
def test_messages_are_role_unique_and_content_restriction_is_distinct_from_archive(storage):
    _, runtime, _, values = storage
    with runtime.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        message(connection, values)
        message(connection, values, role="assistant", origin="assistant-unverified")
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            message(connection, values)
    with runtime.transaction() as connection:
        connection.execute(text("UPDATE class_os.conversation_thread SET status='archived',version=2"))
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE body IS NOT NULL")).scalar_one() == 2
        connection.execute(text("UPDATE class_os.conversation_message SET visibility='restricted',body=NULL"))
        connection.execute(text("""UPDATE class_os.conversation_thread SET title='已清除的会话',status='cleared',
            cleared_at=:at,updated_at=:at,version=3"""), values)
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE body IS NULL")).scalar_one() == 2


@pytest.mark.db
@pytest.mark.parametrize("update", ["state='running'", "state='completed',ended_at=created_at", "input_tokens=1",
    "generation='00000000-0000-0000-0000-000000000001'", "state='invented'"])
def test_queued_rows_cannot_claim_dispatch_terminal_usage_or_unknown_state(storage, update):
    _, runtime, _, values = storage
    with runtime.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            # Fixed parametrized test expressions, never a production API.
            connection.execute(text("UPDATE class_os.conversation_run SET " + update))


@pytest.mark.db
def test_run_sql_matches_cancel_lease_and_unknown_usage_rules(storage):
    _, runtime, _, values = storage
    with runtime.transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        connection.execute(text("""UPDATE class_os.conversation_run SET state='running',version=2,generation=:generation,
            started_at=:at,lease_until=:at+interval '1 minute'"""), {**values, "generation": uuid4()})
        connection.execute(text("""UPDATE class_os.conversation_run SET state='cancel_requested',version=3,
            cancel_requested_at=:at+interval '20 seconds'"""), values)
    for update in ("state='completed',ended_at=started_at+interval '30 seconds'",
                   "state='cancelled',ended_at=started_at+interval '10 seconds'",
                   "state='interrupted',ended_at=started_at+interval '59 seconds'",
                   "state='unknown',ended_at=lease_until"):
        with pytest.raises(IntegrityError):
            with runtime.transaction() as connection:
                connection.execute(text("UPDATE class_os.conversation_run SET " + update))
    with runtime.transaction() as connection:
        connection.execute(text("UPDATE class_os.conversation_run SET state='interrupted',version=4,ended_at=lease_until"))
        assert connection.execute(text("SELECT input_tokens,output_tokens,duration_ms FROM class_os.conversation_run")).one() == (None, None, None)


@pytest.mark.db
def test_profile_role_guard_rejects_an_extra_mutable_column(storage):
    owner, _, _, _ = storage
    with owner.transaction() as connection:
        connection.execute(text("GRANT UPDATE(origin) ON class_os.conversation_message TO class_os_runtime"))
    with owner.transaction(read_only=True) as connection:
        with pytest.raises(RuntimeError, match="role safety"):
            validate_role_guards(connection, profile="conversation-d1")


@pytest.mark.db
def test_profile_role_guard_rejects_unregistered_columns_even_with_plausible_grants(storage):
    owner, _, _, _ = storage
    with owner.transaction() as connection:
        connection.execute(text("ALTER TABLE class_os.conversation_message ADD COLUMN unregistered_payload jsonb"))
        connection.execute(text("GRANT SELECT(unregistered_payload),INSERT(unregistered_payload) ON class_os.conversation_message TO class_os_runtime"))
    with owner.transaction(read_only=True) as connection:
        with pytest.raises(RuntimeError, match="role safety"):
            validate_role_guards(connection, profile="conversation-d1")


@pytest.mark.db
def test_old_core_exit_and_backup_never_silently_omit_new_stores(storage):
    owner, runtime, _, values = storage
    class Core(ExitTransaction):
        def __init__(self, connection):
            self._connection = connection

    with runtime.transaction(read_only=True) as connection:
        with pytest.raises(ValueError, match="incompatible"):
            Core(connection).core_snapshot(values["workspace"])
    with runtime.transaction(read_only=True) as connection:
        with pytest.raises(ValueError, match="incompatible"):
            Core(connection).exit_artifact({}, uuid4(), values["at"])
    with owner.transaction(read_only=True) as connection:
        with pytest.raises(RuntimeError, match="Unregistered"):
            SyntheticBackup._state(connection)


@pytest.mark.db
def test_existing_member_ids_cannot_be_cross_paired(storage):
    owner, runtime, _, values = storage
    second = {**values, "other_student": uuid4(), "other_enrollment": uuid4()}
    with owner.transaction() as connection:
        # Fixed fixture SQL creates another valid member in the same class.
        # Its IDs exist; rejection must be tuple integrity, not missing rows.
        connection.execute(text("""INSERT INTO class_os.student
            SELECT workspace_id,:other_student,'合成学生乙',status,version,created_by,updated_by,created_at,updated_at
            FROM class_os.student WHERE student_id=:student"""), second)
        connection.execute(text("""INSERT INTO class_os.enrollment
            SELECT workspace_id,:other_enrollment,:other_student,class_id,term_id,valid_from,valid_to,status,version,
                   created_by,updated_by,created_at,updated_at
            FROM class_os.enrollment WHERE enrollment_id=:enrollment"""), second)
    with pytest.raises(IntegrityError):
        with runtime.transaction() as connection:
            thread(connection, {**values, "enrollment": second["other_enrollment"]})
    with runtime.transaction() as connection:
        thread(connection, {**values, "student": second["other_student"], "enrollment": second["other_enrollment"]})
