"""An old pending action gets a current factual preview; saved history never does."""
from datetime import date
from uuid import uuid4
import httpx
import pytest
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway
from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from class_os.domain.roster import CreateClass
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.workbench import WorkbenchStore
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_workspace_chat_storage import workspace_chat, roster, identity


@pytest.mark.db
@pytest.mark.parametrize('already_committed', [False, True])
async def test_legacy_first_human_preview_is_durable_but_does_not_rewrite_saved_history(workspace_chat, already_committed):
    chats, _, auth, old_owner, old_runtime, clock, old_store, boundary = workspace_chat
    thread, request = uuid4(), uuid4()
    command = CreateClass(uuid4(), uuid4(), '合成旧草稿班', '合成学期', date(2026, 9, 1), date(2027, 1, 30))
    chats.send(auth, thread, request, '合成旧版待确认操作')
    chats.finish(auth, chats.claim(auth, thread, request), 'completed', '请核对。', command.canonical())
    if already_committed:
        previous = WorkbenchBusinessGateway(boundary, old_store, clock=lambda: clock[0])
        proposal = previous.preview(*auth, command)
        nonce = previous.approve(*auth, proposal.proposal_id, proposal.payload_hash)
        previous.commit(*auth, proposal.proposal_id, uuid4(), nonce)
    owner = Database(old_owner.engine.url, migration=True, profile='classroom-work-d4')
    database = Database(old_runtime.engine.url, profile='classroom-work-d4')
    migrate(owner)
    store = WorkbenchStore(database, old_store.restrictions)
    business = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=PydanticAgentRuntime(query))
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    base = f'/api/workspaces/{auth[3]}'
    prefix = base + f'/workspace-chat/threads/{thread}'
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
            row = (await client.get(prefix)).json()['turns'][0]
            assert row['change_preview'] is None
            preview = await client.post(prefix + f'/turns/{request}/proposal', headers=headers, json={'candidate_hash': row['candidate_hash']})
            if already_committed:
                assert preview.status_code == 409
                assert (await client.get(prefix)).json()['turns'][0]['change_preview'] is None
                return
            assert preview.status_code == 200, preview.text
            first = preview.json()
            assert first['change_preview']['kind'] == 'create'
            assert all(field['before'] is None for field in first['change_preview']['fields'])
            assert query.context(*auth) is None
            assert (await client.get(prefix)).json()['turns'][0]['change_preview'] == first['change_preview']
            rejected = await client.post(base + '/commands/reject', headers=headers, json={'proposal_id': first['proposal_id']})
            assert rejected.status_code == 200
            second = (await client.post(prefix + f'/turns/{request}/proposal', headers=headers, json={'candidate_hash': row['candidate_hash']})).json()
            assert second['change_preview'] == first['change_preview']
            approval = (await client.post(base + '/commands/approve', headers=headers, json={'proposal_id': second['proposal_id'], 'payload_hash': second['payload_hash']})).json()
            saved = await client.post(base + '/commands/commit', headers=headers, json={'proposal_id': second['proposal_id'], 'idempotency_key': str(uuid4()), 'approval': approval['approval']})
            assert saved.status_code == 200, saved.text
            current = (await client.get(prefix)).json()['turns'][0]
            assert current['change_preview'] == first['change_preview'] and current['action_receipt']['receipt_id'] == saved.json()['receipt_id']
    finally:
        owner.close(); database.close()
