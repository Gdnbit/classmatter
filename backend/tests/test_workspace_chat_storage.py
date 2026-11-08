"""D3 transactions on fresh owned PostgreSQL; never the user's runtime."""
from datetime import timedelta
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.application.conversation_control import ConversationBusinessGateway
from class_os.application.roster import CommandRejected
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions
from class_os.infrastructure.workbench import WorkbenchStore
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import validate_surface
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from test_roster_gateway import roster
from test_identity import identity
from test_model_secrets import fixture_codec


@pytest.fixture
def workspace_chat(roster, database_urls, tmp_path):
    boundary, credentials, clock = roster[4], roster[3], roster[6]
    d1_owner = Database(database_urls["migrator"], migration=True, profile="conversation-d1")
    d1_runtime = Database(database_urls["runtime"], profile="conversation-d1")
    migrate(d1_owner)
    restrictions = ProtectedConversationRestrictions(tmp_path, credentials[3], codec=fixture_codec)
    control = ConversationBusinessGateway(boundary, ConversationBusinessStore(d1_runtime, restrictions), clock=lambda: clock[0])
    proposal = control.preview(*credentials, InitializeConversationControl(uuid4()))
    nonce = control.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    control.commit(*credentials, proposal.proposal_id, uuid4(), nonce)
    d1_owner.close(); d1_runtime.close()
    owner = Database(database_urls["migrator"], migration=True, profile="workspace-chat-d3")
    runtime = Database(database_urls["runtime"], profile="workspace-chat-d3")
    migrate(owner)
    store = WorkbenchStore(runtime, restrictions)
    business = WorkspaceChatBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkspaceChatQueryGateway(boundary, store, clock=lambda: clock[0])
    try:
        yield business, query, credentials, owner, runtime, clock, store, boundary
    finally:
        owner.close(); runtime.close()


@pytest.mark.db
def test_no_class_chat_persists_and_reconstructs_without_model(workspace_chat):
    business, query, credentials, owner, runtime, _, store, boundary = workspace_chat
    with owner.transaction(read_only=True) as connection:
        validate_surface(connection, complete=True, profile="workspace-chat-d3")
        validate_role_guards(connection, profile="workspace-chat-d3")
        assert connection.execute(text("SELECT count(*) FROM class_os.school_class")).scalar_one() == 0
    thread, request = uuid4(), uuid4()
    sent = business.send(credentials, thread, request, "合成无班级持久聊天")
    assert sent["state"] == "queued"
    assert business.send(credentials, thread, request, "合成无班级持久聊天") == sent
    with pytest.raises(CommandRejected):
        business.send(credentials, thread, request, "改变原请求")
    ticket = business.claim(credentials, thread, request)
    assert ticket["state"] == "running" and business.claim(credentials, thread, request) is None
    result = business.finish(credentials, ticket, "completed", "合成已保存回答")
    assert result["state"] == "completed"
    rebuilt = WorkspaceChatQueryGateway(boundary, WorkbenchStore(runtime, store.restrictions), clock=business.clock)
    history = rebuilt.history(credentials, thread)
    assert history["turns"][0]["assistant_text"] == "合成已保存回答"
    assert query.listing(credentials)["data"][0]["thread_id"] == thread
    with pytest.raises(CommandRejected):
        business.finish(credentials, ticket, "completed", "重放不得覆盖")


@pytest.mark.db
def test_cancel_and_clear_cannot_release_late_output_or_replay(workspace_chat):
    business, query, credentials, _, _, _, _, _ = workspace_chat
    thread, request = uuid4(), uuid4()
    business.send(credentials, thread, request, "合成等待取消")
    ticket = business.claim(credentials, thread, request)
    cancelled = business.cancel(credentials, thread, request, ticket["version"])
    assert cancelled["state"] == "cancelled"
    with pytest.raises(CommandRejected):
        business.finish(credentials, ticket, "completed", "取消后迟到回答")
    history = query.history(credentials, thread)
    business.control(credentials, thread, history["thread"]["version"], "clear")
    cleared = query.history(credentials, thread)
    assert cleared["thread"]["status"] == "cleared"
    assert all(row["user_text"] is row["assistant_text"] is row["candidate"] is None for row in cleared["turns"])
    with pytest.raises(CommandRejected):
        business.send(credentials, thread, request, "合成等待取消")


@pytest.mark.db
def test_claim_lease_and_scope_guards(workspace_chat):
    business, query, credentials, _, _, clock, _, _ = workspace_chat
    thread, request = uuid4(), uuid4()
    business.send(credentials, thread, request, "合成到期运行")
    with pytest.raises(CommandRejected):
        business.send(credentials, thread, uuid4(), "不能并发启动")
    ticket = business.claim(credentials, thread, request)
    clock[0] += timedelta(minutes=5)
    final = business.finish(credentials, ticket, "completed", "不得发布过期回答")
    assert final["state"] == "unknown" and final["assistant_text"] is None
    with pytest.raises(CommandRejected):
        query.history(credentials, uuid4())
    with pytest.raises(CommandRejected):
        query.listing(credentials, offset=-1)


@pytest.mark.db
def test_runtime_has_no_ddl_delete_or_audit_update(workspace_chat):
    _, _, _, _, runtime, _, _, _ = workspace_chat
    for statement in ("DELETE FROM class_os.workspace_chat_turn", "UPDATE class_os.workspace_chat_audit SET outcome='allowed'",
                      "CREATE TABLE class_os.unapproved_workspace_table(id int)"):
        with pytest.raises(ProgrammingError):
            with runtime.transaction() as connection:
                connection.execute(text(statement))


@pytest.mark.db
def test_full_checkpoint_and_isolated_restore_include_workspace_history(workspace_chat, database_urls, postgres_cluster, request):
    from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected
    business, query, credentials, _, _, _, store, _ = workspace_chat
    thread, key = uuid4(), uuid4()
    business.send(credentials, thread, key, "合成备份聊天")
    ticket = business.claim(credentials, thread, key)
    business.finish(credentials, ticket, "completed", "合成恢复后的回答")
    binaries = Path(request.config.getoption("--pg-root")).resolve()
    if (binaries / "bin").is_dir():
        binaries /= "bin"
    class FixtureRuntime:
        root = store.restrictions.root
        def configuration(self):
            return {"profile": "classmatter-owned-synthetic-workspace-chat-d3", "pg_bin": str(binaries),
                    "port": postgres_cluster["port"], "database": database_urls["migrator"].database}
        def password(self, role):
            assert role == "migrator"
            return ""
        def database(self, role):
            assert role == "migrator"
            return Database(database_urls[role], migration=True, profile="workspace-chat-d3")
        @contextmanager
        def admin(self):
            with psycopg.connect(**postgres_cluster, autocommit=True) as connection:
                yield connection
    backup = SyntheticBackup(FixtureRuntime(), codec=fixture_codec, profile="workspace-chat-d3")
    artifact = backup.create()
    packet, _ = backup._open(artifact)
    assert packet["inventory"]["workspace_chat_thread"]["rows"] == 1
    assert packet["inventory"]["workspace_chat_turn"]["rows"] == 1
    assert packet["inventory"]["workspace_chat_audit"]["rows"] == 3
    result = backup.check_current_restrictions(artifact, store.restrictions)
    assert result["schema_version"] == "classmatter.workspace-chat-backup-check.v1"
    assert result["activation_allowed"] is False
    with pytest.raises(BackupRejected):
        SyntheticBackup(FixtureRuntime(), codec=fixture_codec, profile="workbench-d2").create()
