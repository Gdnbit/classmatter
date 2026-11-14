"""Explicit existing-free-model experiment in a disposable synthetic database.

The previous owned checkout alone opens its already activated configuration.
Only an in-memory DPAPI envelope crosses the child process boundary; never
print keys, credentials or subprocess errors. No automatic model call in CI.
"""
from contextlib import asynccontextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart

from class_os.domain.model_configuration import ModelConfiguration, Protocol
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.local_runtime import protect
from class_os.infrastructure.model_provider import configured_client, model_for_configuration
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from class_os.infrastructure.personal_summary_runtime import PersonalSummaryService
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from test_personal_summary_runtime import classroom_work, workspace_chat, roster, identity, materials, save


SOURCE = r'''
import base64, json, sys
def phase(name):
    sys.stderr.write(name+'\n'); sys.stderr.flush()
phase('bootstrap')
sys.path.insert(0, 'src')
from class_os.infrastructure.local_runtime import LocalRuntime, protect
from class_os.infrastructure.native_setup import NativeSetup
from class_os.infrastructure.workspace_local_runtime import open_services
from class_os.infrastructure.local_model_activation import LocalModelActivation
from class_os.infrastructure.model_control import ModelController
phase('imports-complete')
runtime = LocalRuntime(sys.argv[1], profile='classroom-work-d4')
phase('runtime-validated')
native = NativeSetup(runtime, development=True)
try:
    cookies = native.handle({'operation':'development_access'})['cookies']
    phase('development-access')
finally:
    native.close()
services = open_services(runtime, local_development=True)
phase('services-open')
try:
    auth = cookies['session'], cookies['client'], cookies['csrf'], services.restrictions.workspace_id
    row = services.query.model_configuration(auth)
    active = LocalModelActivation(runtime.root, auth[3]).read()
    assert row and active and (str(row['candidate_id']),row['version']) == (active['candidate_id'],active['version'])
    profile = ModelController.profile(row)
    assert profile.model == 'gemini-3.1-flash-lite'
    assert profile.base_url == 'https://generativelanguage.googleapis.com/v1beta/openai/'
    phase('free-profile-validated')
    key = services.worker.store.model_secrets.open(auth[3],row['candidate_id'],row['version'],profile,bytes(row['sealed']))
    envelope = protect(json.dumps({'key':key.get_secret_value(),'model':profile.model,
        'base_url':profile.base_url,'protocol':profile.protocol.value,'proxy':active['proxy']}).encode())
    sys.stdout.write(base64.b64encode(envelope).decode())
finally:
    services.close()
'''


@pytest.mark.db
@pytest.mark.skipif(os.environ.get('CLASSMATTER_PERSONAL_LIVE') != 'approved-free-only', reason='Explicit approved free-model test only')
async def test_existing_free_model_standing_summary_question_feedback_and_save(classroom_work):
    import base64
    checkout = Path(os.environ['CLASSMATTER_PERSONAL_SOURCE_CHECKOUT']).resolve()
    source = Path(os.environ['CLASSMATTER_PERSONAL_SOURCE_ROOT']).resolve()
    artifacts = Path(os.environ['CLASSMATTER_PERSONAL_ARTIFACT_ROOT']).resolve()
    assert os.name == 'nt' and artifacts.drive.lower() != 'c:'
    assert not artifacts.is_relative_to(Path(__file__).resolve().parents[2])
    remote = subprocess.check_output(['git','remote','get-url','origin'],cwd=checkout,text=True).strip().removesuffix('.git')
    assert remote == 'https://github.com/Gdnbit/classmatter'
    output = artifacts/uuid4().hex
    output.mkdir(parents=True,exist_ok=False)
    try:
        result = subprocess.run([str(checkout/'backend/.venv/Scripts/python.exe'),'-c',SOURCE,str(source)],
            cwd=checkout/'backend',capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as error:
        known = {'bootstrap','imports-complete','runtime-validated','development-access','services-open','free-profile-validated'}
        stages = [line for line in (error.stderr or b'').decode('utf-8',errors='replace').splitlines() if line in known]
        (output/'report.json').write_text(json.dumps([{'stage':'configuration-source','state':'blocked',
            'candidate':None,'answer':None,'tools':[],'diagnostics':[], 'category':'source-timeout',
            'last_phase':stages[-1] if stages else 'process-start','timeout_seconds':60}]),encoding='utf-8')
        pytest.fail('Existing configuration source timed out; bounded local phase evidence retained, no provider call made')
    assert result.returncode == 0, 'Existing approved free configuration unavailable; no credentials copied to logs'
    packet = json.loads(protect(base64.b64decode(result.stdout),decrypt=True))
    profile = ModelConfiguration(Protocol(packet['protocol']),packet['model'],packet['base_url'])
    key, proxy = SecretStr(packet.pop('key')), packet['proxy']
    del packet, result
    traces = []
    class TraceModel(WrapperModel):
        async def request(self, messages, model_settings, model_request_parameters):
            response = await super().request(messages, model_settings, model_request_parameters)
            # This opt-in fixture has synthetic prompts only. Never record
            # client headers, configuration, credentials or request objects.
            traces.append({'parts':[{'tool':p.tool_name,'args':p.args} if isinstance(p,ToolCallPart)
                else {'text':p.content} for p in response.parts if isinstance(p,(TextPart,ToolCallPart))],
                'repairs':[p.content for m in messages for p in m.parts if isinstance(p,RetryPromptPart)]})
            return response
    @asynccontextmanager
    async def context(credentials, request):
        async with configured_client(profile,key,proxy=proxy) as client:
            yield TraceModel(model_for_configuration(profile,client))
    business, query, auth, _, clock, store, _, c, t, _ = classroom_work
    chats = WorkspaceChatBusinessGateway(business.identity,store,clock=lambda:clock[0])
    history = WorkspaceChatQueryGateway(query.identity,store,clock=lambda:clock[0])
    diagnostics, reports = [], []
    sdk = PydanticAgentRuntime(query,model_context=context,provider_label='managed-model',timeout=100,diagnostics=diagnostics.append)
    runtime = WorkspaceChatRuntime(chats,history,sdk)
    service = PersonalSummaryService(runtime)
    service.sessions[auth[3]] = auth
    thread = uuid4()
    def record(stage,row,events):
        reports.append({'stage':stage,'state':row['state'],'candidate':row['candidate'],
            'answer':row['assistant_text'],'tools':[e.payload.get('tool') for e in events if e.type=='tool.completed'],
            'diagnostics':diagnostics[-1:],'trace':list(traces)})
        (output/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    async def turn(stage,text):
        for _ in range(3):
            request = uuid4(); chats.send(auth,thread,request,text)
            events = [e async for e in runtime.stream_queued(auth,thread,request)]
            row = history.turn(auth,thread,request)[1]; record(stage,row,events)
            if row['state']=='completed':
                return row
        pytest.fail('Free provider attempts retained in local report; no success claimed')
    delegation = await turn('delegate','以后持续整理合成成绩班的班级工作小结，需要核对班会主题。')
    assert delegation['candidate'] and delegation['candidate']['title']=='班级小结委托'
    save(business,auth,delegation); materials(classroom_work)
    await service.check(auth[3])  # No new user request asks for a summary.
    question = history.history(auth,thread)['turns'][-1]; record('proactive',question,[])
    if question['state']!='completed':
        question = await turn('explicit-retry','继续整理班级工作小结。')
    assert question['candidate'] is None and '班会主题' in question['assistant_text']
    draft = await turn('answer','班会主题是合作。')
    assert draft['candidate'] and draft['candidate']['title']=='班级工作小结'
    assert all(value in draft['candidate']['body'] for value in ('合成学生0','合成作品核对','老师补充','合作'))
    save(business,auth,draft)
    feedback = await turn('feedback','以后用三条要点整理小结。')
    assert feedback['candidate'] and feedback['candidate']['title']=='班级小结委托'
    save(business,auth,feedback); clock[0]+=timedelta(minutes=2)
    await service.check(auth[3])
    revised = history.history(auth,thread)['turns'][-1]; record('proactive-feedback',revised,[])
    if revised['state']!='completed':
        revised = await turn('explicit-feedback-retry','继续整理班级工作小结。')
    assert revised['candidate'] and revised['candidate']['command']=='document.revise'
    save(business,auth,revised)
    saved = query.document(*auth,c,t,UUID(revised['candidate']['document_id']))
    assert saved['version']==2 and saved['body']==revised['candidate']['body']
    assert len(query.documents(*auth,c,t))==2
    assert sdk.active==0
