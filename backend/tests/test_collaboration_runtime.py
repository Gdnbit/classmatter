"""Two isolated PG workspaces, actual SDK tools/HTTP/BCG; no paid provider."""
from contextlib import ExitStack,contextmanager
from datetime import timedelta
from uuid import UUID,uuid4

import httpx
import pytest
from pydantic_ai.messages import ModelResponse,TextPart,ToolCallPart,ToolReturnPart,UserPromptPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.documents import CreateDocument,ReviseDocument
from class_os.domain.workspace_chat import candidate
from class_os.infrastructure.collaboration_runtime import CollaborationService
from class_os.infrastructure.collaboration_transport import A2AMaterialTransport
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_personal_summary_runtime import assembly,send,save
from test_classroom_work_storage import classroom_work,workspace_chat,roster,identity
from test_classroom_work_storage import classroom_work as classroom_fixture
from conftest import database_urls


@pytest.fixture
def two_classrooms(classroom_work,postgres_cluster,tmp_path):
    with ExitStack() as stack:
        urls = stack.enter_context(contextmanager(database_urls.__wrapped__)(postgres_cluster))
        ident = stack.enter_context(contextmanager(identity.__wrapped__)(urls))
        ro = stack.enter_context(contextmanager(roster.__wrapped__)(ident,urls))
        path = tmp_path/'second-workspace'; path.mkdir()
        workspace = stack.enter_context(contextmanager(workspace_chat.__wrapped__)(ro,urls,path))
        second = stack.enter_context(contextmanager(classroom_fixture.__wrapped__)(workspace))
        yield classroom_work,second


class Network(httpx.AsyncBaseTransport):
    def __init__(self,apps):
        self.apps=apps
        self.offline=set()
        self.lose_next_response=set()

    async def handle_async_request(self,request):
        port=request.url.port
        if port in self.offline:
            raise httpx.ConnectError('Synthetic peer offline',request=request)
        response=await httpx.ASGITransport(app=self.apps[port],raise_app_exceptions=True).handle_async_request(request)
        if port in self.lose_next_response:
            self.lose_next_response.remove(port)
            await response.aread()
            raise httpx.ReadTimeout('Synthetic response lost after durable receive',request=request)
        return response


def model(request):
    def respond(messages,info):
        last=max(i for i,m in enumerate(messages) if any(isinstance(p,UserPromptPart) for p in m.parts))
        returns=[p for m in messages[last:] for p in m.parts if isinstance(p,ToolReturnPart)]
        if not any(p.tool_name=='read_material_collaboration' for p in returns):
            return ModelResponse(parts=[ToolCallPart('read_material_collaboration',{})])
        data=next(p.content for p in reversed(returns) if p.tool_name=='read_material_collaboration')
        if request.text.startswith(('同事提供了材料','重新整理收到的材料')):
            material=next(r for r in data['items'] if r['direction']=='incoming' and r['operation']=='material')
            return ModelResponse(parts=[ToolCallPart('prepare_collected_summary',{'request_id':str(material['request_id']),
                'body':'本周数学教学进度已收集，具体内容见同事提供的材料。'})])
        if '提供本周教学进度' in request.text:
            root=next(r for r in data['items'] if r['direction']=='incoming' and r['operation']=='request')
            return ModelResponse(parts=[ToolCallPart('prepare_material_reply',{'request_id':str(root['request_id']),
                'document_title':'本周教学进度'})])
        return ModelResponse(parts=[ToolCallPart('prepare_material_request',{'peer_name':'合成王老师',
            'request_text':'本周数学教学进度'})])
    return FunctionModel(respond)


async def pair(two_classrooms):
    assemblies=[assembly(f) for f in two_classrooms]
    apps=[]
    for fixture,parts,port in zip(two_classrooms,assemblies,(18441,18442)):
        parts[2].model_factory=model
        apps.append(create_workspace_chat_app(Settings(port=port),worker=fixture[0],query=fixture[1],sdk=parts[2]))
    network=Network(dict(zip((18441,18442),apps)))
    services=[app.state.collaboration for app in apps]
    for service in services:
        service.transport=A2AMaterialTransport(service.proofs,http_transport=network)
    invitations=[]
    for fixture,service,label,port in zip(two_classrooms,services,('合成李老师','合成王老师'),(18441,18442)):
        invitations.append(await service.invitation(fixture[2],label,f'http://127.0.0.1:{port}'))
    for fixture,service,invitation in zip(two_classrooms,services,reversed(invitations)):
        service.business.add_peer(fixture[2],invitation,fixture[7],fixture[8])
    return assemblies,apps,services,network


async def start_request(fixture,parts):
    chats,history,_,runtime,_,_=parts
    thread=uuid4()
    row=await send(runtime,chats,history,fixture[2],thread,'请向合成王老师收集本周数学教学进度，补入小结。')
    assert row['candidate']['command']=='collaboration.request',row
    assert row['change_preview']['fields'][1]['after']=='本周数学教学进度'
    assert not fixture[1].collaboration(fixture[2])['items']
    save(fixture[0],fixture[2],row)
    return thread,row


@pytest.mark.db
async def test_literal_share_does_not_offer_document_mutation_or_invent_material(two_classrooms):
    a,b=two_classrooms
    parts,_,services,_=await pair(two_classrooms)
    await start_request(a,parts[0]);await services[0].check(a[2][3])
    incoming=services[1].query.read(b[2])['items'][0]
    document=CreateDocument(uuid4(),b[7],b[8],'本周教学进度','只记录已核对的第三单元进度。','markdown')
    b[6](document)
    observed=[]
    def provider(request):
        respond=model(request)
        def check(messages,info):
            names={tool.name for tool in info.function_tools}
            observed.append(names)
            assert names=={'read_material_collaboration','prepare_material_reply','read_task_progress'}
            if any(isinstance(p,ToolReturnPart) and p.tool_name=='prepare_material_reply'
                   and p.content.get('status')=='already-prepared' for m in messages for p in m.parts):
                return ModelResponse(parts=[TextPart('已发送，内部请求ID：'+str(incoming['request_id']))])
            return respond.function(messages,info)
        return FunctionModel(check)
    parts[1][2].model_factory=provider
    row=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],
        '请提供本周教学进度给合成李老师。')
    assert observed and row['candidate']['command']=='collaboration.material.share',row
    assert row['candidate']['body']==document.body
    assert row['candidate']['expected_version']==1
    assert b[1].document(*b[2],b[7],b[8],document.document_id)['body']==document.body
    assert len(services[1].query.read(b[2])['items'])==1,'A candidate does not send material'
    save(b[0],b[2],row)
    queued=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],
        '请提供本周教学进度给合成李老师。')
    assert queued['candidate'] is None and queued['assistant_text']=='材料正在发送，请稍后查看。'
    await services[1].check(b[2][3])
    repeated=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],
        '请提供本周教学进度给合成李老师。')
    assert repeated['state']=='completed' and repeated['candidate'] is None,repeated
    assert repeated['assistant_text']=='材料已发送，无需重复提供。'
    assert len(services[1].query.read(b[2])['items'])==2
    assert b[1].document(*b[2],b[7],b[8],document.document_id)['version']==1


@pytest.mark.db
async def test_two_workspaces_material_to_summary_save_and_refresh(two_classrooms):
    a,b=two_classrooms
    parts,_,services,_=await pair(two_classrooms)
    sa,sb=services
    thread,request=await start_request(a,parts[0])
    root=UUID(request['candidate']['request_id'])
    await sa.check(a[2][3])
    assert sa.query.read(a[2])['items'][0]['status']=='delivered'
    incoming=sb.query.read(b[2])['items'][0]
    assert incoming['direction']=='incoming' and incoming['request_id']==root
    assert parts[1][1].history(b[2],incoming['thread_id'])['turns'][0]['origin']=='collaboration'
    assert parts[1][1].listing(b[2])['data'][0]['summary_attention']
    document=CreateDocument(uuid4(),b[7],b[8],'本周教学进度','数学完成第三单元，周五已核对练习。','markdown')
    b[6](document)
    reply=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],'提供本周教学进度给合成李老师。')
    assert reply['candidate']['command']=='collaboration.material.share'
    assert reply['candidate']['body']==document.body
    assert len(sa.query.read(a[2])['items'])==1
    save(b[0],b[2],reply)
    await sb.check(b[2][3]);await sa.check(a[2][3])
    prepared=parts[0][1].history(a[2],thread)['turns'][-1]
    assert prepared['origin']=='collaboration' and prepared['candidate']['command']=='collaboration.summary.save'
    assert '合成王老师提供：《本周教学进度》（第1版）' in prepared['candidate']['body']
    assert prepared['candidate']['body'].endswith(document.body)
    assert not a[1].documents(*a[2],a[7],a[8]),'Neither remote receipt nor Agent output saves a summary'
    receipt=save(a[0],a[2],prepared)
    refreshed=parts[0][1].history(a[2],thread)['turns'][-1]
    assert refreshed['action_receipt']['resource_id']==receipt.resource_id
    assert refreshed['change_preview']==prepared['change_preview']
    assert a[1].document(*a[2],a[7],a[8],receipt.resource_id)['body']==prepared['candidate']['body']
    assert all(r['status']=='saved' for r in sa.query.read(a[2])['items'])
    await sa.check(a[2][3]);await sb.check(b[2][3])
    assert len(a[1].documents(*a[2],a[7],a[8]))==1
    with pytest.raises(CommandRejected):
        a[0].preview(*a[2],candidate(prepared['candidate']))
    with pytest.raises(CommandRejected):
        b[1].documents(*b[2],a[7],a[8])
    for fixture in two_classrooms:
        with fixture[3].transaction(read_only=True) as connection:
            from class_os.infrastructure.persistence.role_guards import validate_role_guards
            from class_os.infrastructure.collaboration_store import validate_collaboration_integrity
            validate_role_guards(connection,profile='classroom-work-d4')
            validate_collaboration_integrity(connection)


@pytest.mark.db
async def test_offline_lost_receipt_restart_and_duplicate_delivery(two_classrooms):
    a,b=two_classrooms
    parts,_,services,network=await pair(two_classrooms)
    sa,sb=services
    thread,row=await start_request(a,parts[0])
    network.offline.add(18442)
    await sa.check(a[2][3])
    assert sb.query.read(b[2])['items']==[]
    assert sa.query.read(a[2])['items'][0]['status']=='queued'
    # Recreate the coordinator, not the database or its durable outbox.
    sa=CollaborationService(parts[0][3])
    sa.transport=A2AMaterialTransport(sa.proofs,http_transport=network)
    await sa.watch(a[2])
    network.offline.clear();network.lose_next_response.add(18442)
    for fixture in two_classrooms: fixture[4][0]+=timedelta(seconds=6)
    await sa.check(a[2][3])
    assert len(sb.query.read(b[2])['items'])==1
    assert sa.query.read(a[2])['items'][0]['delivered_at'] is None
    for fixture in two_classrooms: fixture[4][0]+=timedelta(seconds=11)
    await sa.check(a[2][3])
    assert sa.query.read(a[2])['items'][0]['status']=='delivered'
    assert len(sb.query.read(b[2])['items'])==1
    incoming=sb.query.read(b[2])['items'][0]
    assert len(parts[1][1].history(b[2],incoming['thread_id'])['turns'])==1
    with a[3].transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT attempts FROM class_os.collaboration_message')).scalar_one()==3
    # Other workspace credentials cannot be applied to the sender's QG.
    from class_os.application.identity import IdentityDenied
    with pytest.raises(IdentityDenied):
        sa.query.read(b[2])


@pytest.mark.db
async def test_stale_shared_document_and_summary_cas_do_not_save_or_send_twice(two_classrooms):
    a,b=two_classrooms
    parts,_,services,_=await pair(two_classrooms)
    sa,sb=services
    thread,_=await start_request(a,parts[0]);await sa.check(a[2][3])
    incoming=sb.query.read(b[2])['items'][0]
    document=CreateDocument(uuid4(),b[7],b[8],'本周教学进度','第一版：第三单元。','markdown')
    b[6](document)
    reply=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],'提供本周教学进度给合成李老师。')
    proposal=b[0].preview(*b[2],candidate(reply['candidate']))
    approval=b[0].approve(*b[2],proposal.proposal_id,proposal.payload_hash)
    b[6](ReviseDocument(document.document_id,b[7],b[8],1,document.title,'第二版：第三单元及复习。','markdown'))
    with pytest.raises(CommandRejected):
        b[0].commit(*b[2],proposal.proposal_id,uuid4(),approval)
    assert len(sb.query.read(b[2])['items'])==1
    fresh=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],'提供本周教学进度给合成李老师。')
    assert fresh['candidate']['expected_version']==2
    save(b[0],b[2],fresh)
    # Existing summary content is retained without asking the model to copy it.
    old=CreateDocument(uuid4(),a[7],a[8],'班级工作小结','原有小结，不能丢失。','markdown')
    a[6](old)
    await sb.check(b[2][3]);await sa.check(a[2][3])
    prepared=parts[0][1].history(a[2],thread)['turns'][-1]
    assert prepared['candidate']['body'].startswith(old.body)
    assert '（第2版）' in prepared['candidate']['body']
    assert prepared['change_preview']['kind']=='edit'
    p=a[0].preview(*a[2],candidate(prepared['candidate']))
    proof=a[0].approve(*a[2],p.proposal_id,p.payload_hash)
    a[6](ReviseDocument(old.document_id,a[7],a[8],1,old.title,'另一处人工修改，继续保留。','markdown'))
    with pytest.raises(CommandRejected):
        a[0].commit(*a[2],p.proposal_id,uuid4(),proof)
    assert a[1].document(*a[2],a[7],a[8],old.document_id)['version']==2
    assert prepared['change_preview']==parts[0][1].history(a[2],thread)['turns'][-1]['change_preview']


@pytest.mark.db
async def test_peer_proof_binding_revocation_and_receive_audit_rollback(two_classrooms,monkeypatch):
    from class_os.domain.collaboration import MaterialMessage
    from class_os.infrastructure.collaboration_store import CollaborationTransaction
    from class_os.infrastructure.collaboration_transport import message,receipt_response
    from a2a.types import SendMessageRequest
    from google.protobuf.json_format import MessageToDict
    a,b=two_classrooms
    parts,apps,services,network=await pair(two_classrooms)
    sa,sb=services
    _,row=await start_request(a,parts[0])
    item=sa.query.read(a[2])['items'][0]
    root=item['request_id']
    value=MaterialMessage(message_id=root,request_id=root,sender=a[2][3],receiver=b[2][3],
        operation='request',title=item['title'],body=item['body'])
    proof=sa.proofs.sign(a[2],b[2][3],root,value.digest())
    wire={'jsonrpc':'2.0','id':str(uuid4()),'method':'SendMessage',
          'params':MessageToDict(SendMessageRequest(message=message(value.model_dump(mode='json'),root)))}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[1]),base_url='http://127.0.0.1:18442') as client:
        async def oversized():
            yield b' '*65000
            yield b' '*1000
        assert (await client.post('/api/collaboration/a2a',content=oversized())).status_code==413
        assert (await client.post('/api/collaboration/a2a',json=wire,headers={'Authorization':'Bearer '+proof[:-4]+'xxxx'})).status_code==403
        wrong=MaterialMessage(**(value.model_dump()|{'body':'篡改请求'}))
        changed=wire|{'params':MessageToDict(SendMessageRequest(message=message(wrong.model_dump(mode='json'),root)))}
        assert (await client.post('/api/collaboration/a2a',json=changed,headers={'Authorization':'Bearer '+proof})).status_code==403
        assert (await client.post('/api/collaboration/a2a',json=wire,headers={'Authorization':'Bearer '+proof,'Origin':'http://127.0.0.1:18442'})).status_code==403
    assert sb.query.read(b[2])['items']==[]
    audit=CollaborationTransaction.audit
    def unavailable(self,binding,action,outcome,now,metadata):
        if action=='collaboration.receive' and outcome=='allowed':
            raise RuntimeError('Synthetic receive audit unavailable')
        return audit(self,binding,action,outcome,now,metadata)
    monkeypatch.setattr(CollaborationTransaction,'audit',unavailable)
    await sa.check(a[2][3])
    monkeypatch.setattr(CollaborationTransaction,'audit',audit)
    assert sb.query.read(b[2])['items']==[]
    assert not parts[1][1].listing(b[2])['data'],'Failed receive must not leave a ghost chat'
    for fixture in two_classrooms:fixture[4][0]+=timedelta(seconds=6)
    await sa.check(a[2][3])
    assert len(sb.query.read(b[2])['items'])==1
    # Even a genuinely signed second message cannot change the first payload.
    changed_proof=sa.proofs.sign(a[2],b[2][3],root,wrong.digest())
    with pytest.raises(CommandRejected):
        await sb.receive(wrong,changed_proof)
    peer=sa.query.read(a[2])['peers'][0]
    sa.business.revoke_peer(a[2],peer['peer_id'],peer['version'])
    assert sa.query.read(a[2])['items'][0]['status']=='stopped'
    peer_b=sb.query.read(b[2])['peers'][0]
    sb.business.revoke_peer(b[2],peer_b['peer_id'],peer_b['version'])
    assert not parts[1][1].listing(b[2])['data'][0]['summary_attention']
    from dataclasses import replace
    with pytest.raises(CommandRejected):
        a[0].preview(*a[2],replace(candidate(row['candidate']),request_id=uuid4()))
    assert len(sa.query.read(a[2])['items'])==1,'Revoking retains all history'


@pytest.mark.db
async def test_retry_budget_clear_projection_and_model_failure_keep_material(two_classrooms):
    a,b=two_classrooms
    parts,_,services,network=await pair(two_classrooms)
    sa,sb=services
    thread,_=await start_request(a,parts[0])
    root=sa.query.read(a[2])['items'][0]['message_id']
    # Arrange an exhausted transport in this disposable DB; this is not a
    # shortened production timeout or proof that a remote service was called.
    with a[3].transaction() as connection:
        connection.execute(text('UPDATE class_os.collaboration_message SET attempts=12'),{})
    assert sa.query.read(a[2])['items'][0]['status']=='retry-needed'
    await sa.check(a[2][3]);assert not sb.query.read(b[2])['items']
    sa.business.retry(a[2],root)
    await sa.check(a[2][3]);assert len(sb.query.read(b[2])['items'])==1
    sa.business.retry(a[2],root)
    assert sa.query.read(a[2])['items'][0]['delivered_at'] is not None
    incoming=sb.query.read(b[2])['items'][0]
    # The synthetic system notice must never be recalled as the teacher's note.
    assert not parts[1][1].recall(b[2],incoming['thread_id'],'同事',before=2)['items']
    b[6](CreateDocument(uuid4(),b[7],b[8],'本周教学进度','数学完成第三单元。','markdown'))
    reply=await send(parts[1][3],parts[1][0],parts[1][1],b[2],incoming['thread_id'],'提供本周教学进度给合成李老师。')
    save(b[0],b[2],reply)
    def unavailable(request):
        def fail(messages,info):raise TimeoutError('Synthetic model unavailable')
        return FunctionModel(fail)
    parts[0][2].model_factory=unavailable
    await sb.check(b[2][3]);await sa.check(a[2][3])
    failed=parts[0][1].history(a[2],thread)['turns'][-1]
    assert failed['state']=='failed' and failed['origin']=='collaboration'
    assert len(sa.query.read(a[2])['items'])==2 and not a[1].documents(*a[2],a[7],a[8])
    parts[0][2].model_factory=model
    prepared=await send(parts[0][3],parts[0][0],parts[0][1],a[2],thread,'重新整理收到的材料。')
    assert prepared['candidate']['command']=='collaboration.summary.save'
    save(a[0],a[2],prepared)
    header=parts[0][1].history(a[2],thread)['thread']
    parts[0][0].control(a[2],thread,header['version'],'clear')
    assert sa.query.read(a[2],thread_id=thread)['items']==[]
    assert len(sa.query.read(a[2])['items'])==2,'Clearing chat does not delete confirmed material history'


@pytest.mark.db
async def test_revoked_queue_does_not_starve_active_peer_and_concurrent_receive_is_unique(two_classrooms):
    import asyncio
    from dataclasses import replace
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from class_os.domain.collaboration import Invitation,MaterialMessage
    a,b=two_classrooms
    parts,_,services,_=await pair(two_classrooms)
    sa,sb=services
    thread,row=await start_request(a,parts[0])
    old=Invitation(workspace_id=uuid4(),name='合成停止协作同事',endpoint='http://127.0.0.1:18443',
        public_key=Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex())
    sa.business.add_peer(a[2],old,a[7],a[8])
    orphan=replace(candidate(row['candidate']),request_id=uuid4(),peer_id=old.workspace_id)
    a[6](orphan)
    sa.business.revoke_peer(a[2],old.workspace_id,1)
    # Put the stopped contact first in the disposable queue, so an exception
    # here would prevent the independently authorized receiver being reached.
    with a[3].transaction() as connection:
        connection.execute(text('UPDATE class_os.collaboration_message SET created_at=created_at-interval \'1 second\' WHERE peer_id=:peer'),{'peer':old.workspace_id})
    await sa.check(a[2][3])
    incoming=sb.query.read(b[2])['items']
    assert len(incoming)==1
    value=MaterialMessage(message_id=incoming[0]['message_id'],request_id=incoming[0]['request_id'],
        sender=a[2][3],receiver=b[2][3],operation='request',title=incoming[0]['title'],body=incoming[0]['body'])
    proof=sa.proofs.sign(a[2],b[2][3],value.message_id,value.digest())
    receipts=await asyncio.gather(*(sb.receive(value,proof) for _ in range(3)))
    assert all(receipts) and len(sb.query.read(b[2])['items'])==1
    assert len(parts[1][1].history(b[2],incoming[0]['thread_id'])['turns'])==1
    stopped=next(r for r in sa.query.read(a[2])['items'] if r['peer_id']==old.workspace_id)
    assert stopped['delivered_at'] is None and stopped['status']=='stopped'
    current=parts[0][1].history(a[2],thread)['thread']
    parts[0][0].control(a[2],thread,current['version'],'archive')
    assert all(r['status']=='stopped' for r in sa.query.read(a[2])['items'])
