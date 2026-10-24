"""Real synthetic BCG/ISB/QG transactions; never uses the user's runtime."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4
from types import SimpleNamespace
import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import ProgrammingError

from class_os.application.audit import AuditUnavailable
from class_os.application.conversation_control import ConversationBusinessGateway, ConversationQueryGateway
from class_os.application.roster import BusinessGateway, CommandRejected
from class_os.domain.conversation_control import InitializeConversationControl, ClearConversation, decode_control
from class_os.domain.roster import decode
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.conversation_control import ConversationTransaction
from class_os.domain.activity import CreateRecord, CreateTask
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions, FILE_NAME
from test_durable_conversation_storage import storage, roster, identity, thread, turn, queued, message
from test_model_secrets import fixture_codec


@pytest.fixture
def control(storage, roster, tmp_path):
    owner, runtime, private, values = storage
    port = ProtectedConversationRestrictions(tmp_path, values["workspace"], codec=fixture_codec)
    store = ConversationBusinessStore(runtime, port)
    gateway = ConversationBusinessGateway(roster[4], store, clock=lambda: roster[6][0])
    query = ConversationQueryGateway(roster[4], store, clock=lambda: roster[6][0])
    return gateway, query, store, port, owner, values, roster[3], roster[6], private


def approve(data, command):
    gateway, _, _, _, _, _, credentials, *_ = data
    proposal = gateway.preview(*credentials, command)
    nonce = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash) if proposal.risk != "W1" else None
    return proposal, nonce


def commit(data, command):
    proposal, nonce = approve(data, command)
    receipt = data[0].commit(*data[6], proposal.proposal_id, uuid4(), nonce)
    return receipt


@pytest.fixture
def populated(control):
    commit(control, InitializeConversationControl(uuid4()))
    with control[4].transaction() as connection:
        values = control[5]
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        message(connection, values)
    return control


def clear(data):
    values = data[5]
    return ClearConversation(values["thread"], values["class"], values["term"], 1)


def history(data):
    values = data[5]
    return data[1].conversation_history(*data[6], values["class"], values["term"], values["thread"])


def test_control_commands_closed_and_not_admitted_by_r1_decoder():
    for command in (InitializeConversationControl(uuid4()), ClearConversation(uuid4(), uuid4(), uuid4(), 2)):
        assert decode_control(command.canonical()) == command
        with pytest.raises(ValueError):
            decode(command.canonical())
        with pytest.raises(ValueError):
            decode_control({**command.canonical(), "unknown": True})
    for version in (True, 0, -1, 2147483647):
        with pytest.raises(ValueError):
            ClearConversation(uuid4(), uuid4(), uuid4(), version)
    for value in (True, None, 1, {}):
        with pytest.raises(ValueError):
            decode_control({"command": "conversation.control.initialize", "authority_id": value})


@pytest.mark.db
def test_clear_preserves_business_facts_and_tasks(populated):
    values = populated[5]
    record = CreateRecord("record.create", uuid4(), values["class"], values["term"], values["student"],
                          "ordinary_fact", values["at"], "合成业务事实不属于聊天", "")
    commit(populated, record)
    commit(populated, CreateTask("task.create", uuid4(), values["class"], values["term"], "合成待办继续存在"))
    def snapshot():
        with populated[4].transaction(read_only=True) as connection:
            return tuple(connection.execute(text("SELECT to_jsonb(t)::text FROM class_os." + table + " t")).scalars().all()
                         for table in ("record_revision", "manual_task"))
    before = snapshot()
    assert all(before)
    commit(populated, clear(populated))
    assert snapshot() == before


@pytest.mark.db
def test_clear_real_history_body_title_anchor_and_idempotent_receipt(populated):
    gateway, _, _, port, owner, values, credentials, *_ = populated
    before = history(populated)
    assert before.messages[0].content.text == "合成原文"
    proposal, nonce = approve(populated, clear(populated))
    assert proposal.risk == "X"
    original = (port.root / FILE_NAME).read_bytes()
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4())
    assert (port.root / FILE_NAME).read_bytes() == original
    key = uuid4()
    receipt = gateway.commit(*credentials, proposal.proposal_id, key, nonce)
    assert gateway.commit(*credentials, proposal.proposal_id, key, nonce) == receipt
    assert receipt.version == 2 and receipt.resource_id == values["thread"]
    view = history(populated)
    assert view.title == "已清除的会话" and view.status == "cleared" and view.messages == ()
    assert port.read().head.epoch == 1
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT body,visibility FROM class_os.conversation_message")).one() == (None, "restricted")
        assert connection.execute(text("SELECT state,version FROM class_os.conversation_run")).one() == ("cancelled", 2)
        assert connection.execute(text("SELECT count(*) FROM class_os.student")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_turn")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE receipt_id=:r"), {"r": receipt.receipt_id}).scalar_one() == 2


@pytest.mark.db
def test_audit_failure_keeps_external_restriction_and_denies_until_explicit_retry(populated, monkeypatch):
    gateway, _, store, port, owner, values, credentials, *_ = populated
    proposal, nonce = approve(populated, clear(populated))
    key = uuid4()
    old = port.read().head
    original = store.audit
    monkeypatch.setattr(store, "audit", lambda *args: None)
    with pytest.raises(AuditUnavailable):
        gateway.commit(*credentials, proposal.proposal_id, key, nonce)
    monkeypatch.setattr(store, "audit", original)
    assert port.compare(old).state == "one-ahead"
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT status,version FROM class_os.conversation_thread")).one() == ("active", 1)
        assert connection.execute(text("SELECT body FROM class_os.conversation_message")).scalar_one() == "合成原文"
        assert connection.execute(text("SELECT epoch FROM class_os.conversation_control")).scalar_one() == 0
    with pytest.raises(CommandRejected):
        history(populated)
    receipt = gateway.commit(*credentials, proposal.proposal_id, key, nonce)
    assert receipt.version == 2 and port.read().head.epoch == 1
    assert history(populated).messages == ()


@pytest.mark.db
def test_file_failure_before_publication_preserves_visible_history(populated, monkeypatch):
    gateway, _, _, port, _, _, credentials, *_ = populated
    proposal, nonce = approve(populated, clear(populated))
    original = port._publish
    monkeypatch.setattr(port, "_publish", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic failure")))
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4(), nonce)
    monkeypatch.setattr(port, "_publish", original)
    assert port.read().head.epoch == 0 and history(populated).messages


@pytest.mark.db
def test_missing_corrupt_and_rolled_back_anchor_never_release_history(populated):
    port, owner = populated[3:5]
    path = port.root / FILE_NAME
    saved = path.read_bytes()
    path.unlink()
    with pytest.raises(CommandRejected):
        history(populated)
    with pytest.raises(CommandRejected):
        populated[0].preview(*populated[6], InitializeConversationControl(uuid4()))
    path.write_bytes(b"corrupt-fixture-only")
    with pytest.raises(CommandRejected):
        history(populated)
    path.write_bytes(saved)
    old = port.read().head
    commit(populated, clear(populated))
    with owner.transaction() as connection:
        connection.execute(text("UPDATE class_os.conversation_control SET epoch=0,head_hash=:h"), {"h": old.digest})
    with pytest.raises(CommandRejected):
        history(populated)
    assert port.read().head.epoch == 1


@pytest.mark.db
def test_scope_versions_recent_auth_and_r1_gateway_cannot_clear(populated):
    command = clear(populated)
    for candidate in (replace(command, class_id=uuid4()), replace(command, term_id=uuid4()),
                      replace(command, thread_id=uuid4()), replace(command, expected_version=2)):
        with pytest.raises(CommandRejected):
            populated[0].preview(*populated[6], candidate)
    r1 = BusinessGateway(populated[0].identity, populated[2], clock=populated[0].clock)
    with pytest.raises(CommandRejected):
        r1.preview(*populated[6], command)
    populated[7][0] += timedelta(minutes=5, seconds=1)
    with pytest.raises(CommandRejected):
        populated[0].preview(*populated[6], command)
    assert populated[3].read().head.epoch == 0


@pytest.mark.db
@pytest.mark.parametrize("state,expired,expected", [("running", False, "unknown"), ("cancel_requested", False, "unknown"),
                                                    ("running", True, "interrupted"), ("cancel_requested", True, "interrupted")])
def test_live_runs_fenced_without_false_provider_cancellation(populated, state, expired, expected):
    values = {**populated[5], "generation": uuid4(), "state": state}
    with populated[4].transaction() as connection:
        connection.execute(text("""UPDATE class_os.conversation_run SET state=CAST(:state AS varchar(20)),version=2,
            generation=:generation,started_at=:at,lease_until=:at+interval '1 minute',
            cancel_requested_at=CASE WHEN CAST(:state AS text)='cancel_requested' THEN :at ELSE NULL END"""), values)
    if expired:
        populated[7][0] += timedelta(minutes=1)
    commit(populated, clear(populated))
    with populated[4].transaction() as connection:
        assert connection.execute(text("SELECT state,version FROM class_os.conversation_run")).one() == (expected, 3)
        late = connection.execute(text("""UPDATE class_os.conversation_run SET state='completed',version=3,ended_at=:at
            WHERE workspace_id=:workspace AND run_id=:run AND generation=:generation AND version=2 AND state='running'"""), values)
        assert late.rowcount == 0


@pytest.mark.db
def test_same_key_concurrent_retries_do_not_duplicate_clear(populated):
    proposal, nonce = approve(populated, clear(populated))
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: populated[0].commit(*populated[6], proposal.proposal_id, key, nonce), range(2)))
    assert receipts[0] == receipts[1] and populated[3].read().head.epoch == 1


@pytest.mark.db
def test_control_anchor_roles_are_limited(control):
    commit(control, InitializeConversationControl(uuid4()))
    with control[8].transaction() as connection, pytest.raises(ProgrammingError):
        connection.execute(text("SELECT * FROM class_os.conversation_control"))
    for sql in ("UPDATE class_os.conversation_control SET authority_id=gen_random_uuid()",
                "DELETE FROM class_os.conversation_control", "TRUNCATE class_os.conversation_control"):
        with control[2].database.transaction() as connection, pytest.raises(ProgrammingError):
            connection.execute(text(sql))


@pytest.mark.db
def test_initial_audit_failure_reuses_same_empty_authority_not_a_reset(control, monkeypatch):
    command = InitializeConversationControl(uuid4())
    proposal, nonce = approve(control, command)
    original = control[2].audit
    monkeypatch.setattr(control[2], "audit", lambda *args: None)
    with pytest.raises(AuditUnavailable):
        control[0].commit(*control[6], proposal.proposal_id, uuid4(), nonce)
    monkeypatch.setattr(control[2], "audit", original)
    assert control[3].read().head.authority_id == command.authority_id
    with pytest.raises(CommandRejected):
        control[0].preview(*control[6], InitializeConversationControl(uuid4()))
    control[0].commit(*control[6], proposal.proposal_id, uuid4(), nonce)
    with pytest.raises(CommandRejected):
        control[0].preview(*control[6], command)


@pytest.mark.db
@pytest.mark.parametrize("failure", ["sql", "file-after", "run-noop"])
def test_late_failure_preserves_pending_evidence_and_retry(populated, monkeypatch, failure):
    proposal, nonce = approve(populated, clear(populated))
    original = populated[3].read().head
    key = uuid4()
    with monkeypatch.context() as patch:
        if failure == "sql":
            mutate = ConversationTransaction._mutate
            def fault(tx, statement, values, **options):
                if "UPDATE class_os.conversation_control" in str(statement):
                    raise RuntimeError("synthetic SQL persistence failure")
                return mutate(tx, statement, values, **options)
            patch.setattr(ConversationTransaction, "_mutate", fault)
            error = RuntimeError
        elif failure == "run-noop":
            execute = Connection.execute
            def fault(connection, statement, *args, **kwargs):
                if "UPDATE class_os.conversation_run" in str(statement):
                    return SimpleNamespace(rowcount=0)
                return execute(connection, statement, *args, **kwargs)
            patch.setattr(Connection, "execute", fault)
            error = RuntimeError
        else:
            publish = populated[3]._publish
            def fault(*args, **kwargs):
                publish(*args, **kwargs)
                raise OSError("synthetic lost publication response")
            patch.setattr(populated[3], "_publish", fault)
            error = CommandRejected
        with pytest.raises(error):
            populated[0].commit(*populated[6], proposal.proposal_id, key, nonce)
    assert populated[3].compare(original).state == "one-ahead"
    with pytest.raises(CommandRejected):
        history(populated)
    populated[0].commit(*populated[6], proposal.proposal_id, key, nonce)
    assert populated[3].read().head.epoch == 1 and history(populated).messages == ()


@pytest.mark.db
def test_partial_row_rollback_cannot_resurrect_with_current_anchor(populated):
    commit(populated, clear(populated))
    with populated[4].transaction() as connection:
        connection.execute(text("""UPDATE class_os.conversation_thread SET status='active',title='合成旧标题',version=1,cleared_at=NULL"""))
        connection.execute(text("UPDATE class_os.conversation_message SET visibility='visible',body='合成旧正文'"))
    with pytest.raises(CommandRejected):
        history(populated)


@pytest.mark.db
@pytest.mark.parametrize("phase", ["approve", "commit"])
def test_recent_auth_checked_again_after_preview(populated, phase):
    proposal = populated[0].preview(*populated[6], clear(populated))
    nonce = populated[0].approve(*populated[6], proposal.proposal_id, proposal.payload_hash) if phase == "commit" else None
    populated[7][0] += timedelta(minutes=5, seconds=1)
    with pytest.raises(CommandRejected):
        if phase == "approve":
            populated[0].approve(*populated[6], proposal.proposal_id, proposal.payload_hash)
        else:
            populated[0].commit(*populated[6], proposal.proposal_id, uuid4(), nonce)
    assert populated[3].read().head.epoch == 0


@pytest.mark.db
def test_pending_cannot_be_claimed_by_different_clear(populated, monkeypatch):
    second = {**populated[5], "thread": uuid4()}
    with populated[4].transaction() as connection:
        thread(connection, second)
    proposal, nonce = approve(populated, clear(populated))
    with monkeypatch.context() as patch:
        patch.setattr(populated[2], "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            populated[0].commit(*populated[6], proposal.proposal_id, uuid4(), nonce)
    with pytest.raises(CommandRejected):
        populated[0].preview(*populated[6], ClearConversation(second["thread"], second["class"], second["term"], 1))
    assert populated[3].read().head.epoch == 1


@pytest.mark.db
def test_initialization_never_claims_preexisting_history(control):
    with control[4].transaction() as connection:
        thread(connection, control[5])
    with pytest.raises(CommandRejected):
        control[0].preview(*control[6], InitializeConversationControl(uuid4()))
    assert not (control[3].root / FILE_NAME).exists()


@pytest.mark.db
def test_history_keeps_whole_last_fifty_turns_in_role_order_at_equal_times(populated):
    base = populated[5]
    with populated[4].transaction() as connection:
        # Finish first turn before creating another, preserving the real active slot.
        connection.execute(text("""UPDATE class_os.conversation_run SET state='completed',version=3,
            generation=:g,started_at=:at,lease_until=:at+interval '1 minute',ended_at=:at"""), {**base, "g": uuid4()})
        message(connection, base, role="assistant", origin="assistant-unverified", body="合成答复0")
        for ordinal in range(2, 52):
            values = {**base, "turn": uuid4(), "run": uuid4(), "key": uuid4()}
            turn(connection, values, ordinal)
            connection.execute(text("""INSERT INTO class_os.conversation_run
                (workspace_id,thread_id,turn_id,run_id,state,version,created_at,queued_until,generation,started_at,lease_until,ended_at)
                VALUES(:workspace,:thread,:turn,:run,'completed',3,:at,:at+interval '1 minute',:g,:at,:at+interval '1 minute',:at)"""),
                {**values, "g": uuid4()})
            for role, origin, order in (("user", "user-original", 1), ("assistant", "assistant-unverified", 0)):
                # Reverse UUID order deliberately: random/time ordering is not turn order.
                connection.execute(text("""INSERT INTO class_os.conversation_message
                    (workspace_id,thread_id,turn_id,message_id,role,origin,visibility,body,created_at)
                    VALUES(:workspace,:thread,:turn,:id,:role,:origin,'visible',:body,:at)"""),
                    {**values, "id": UUID(int=ordinal * 2 + order), "role": role, "origin": origin, "body": f"合成{ordinal}{role}"})
    view = history(populated)
    assert view.truncated and len(view.messages) == 100
    assert [item.content.role for item in view.messages] == ["user", "assistant"] * 50
    assert view.messages[0].content.text == "合成2user" and view.messages[-1].content.text == "合成51assistant"


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI plus PostgreSQL composition")
def test_real_dpapi_and_pg_clear_composition(control):
    values = control[5]
    actual = ProtectedConversationRestrictions(control[3].root, values["workspace"])
    control[2].restrictions = actual
    commit(control, InitializeConversationControl(uuid4()))
    with control[4].transaction() as connection:
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        message(connection, values)
    assert history(control).messages
    commit(control, clear(control))
    assert history(control).messages == () and actual.read().head.epoch == 1
    sealed = (actual.root / FILE_NAME).read_bytes()
    assert str(values["thread"]).encode() not in sealed
    corrupted = bytearray(sealed)
    corrupted[len(corrupted) // 2] ^= 1
    (actual.root / FILE_NAME).write_bytes(corrupted)
    with pytest.raises(CommandRejected):
        history(control)
