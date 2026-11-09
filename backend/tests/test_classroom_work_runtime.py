"""Actual SDK/HTTP/PG classroom tools; only FunctionModel is synthetic."""
from uuid import uuid4
import httpx
import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


@pytest.mark.db
async def test_agent_exams_scores_layout_assign_swap_and_original_receipts(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    selected, seen = [None], []
    def factory(request):
        def respond(messages, info):
            names = {tool.name for tool in info.function_tools}
            assert 'read_classroom_work' in names and not names & {'commit', 'approve', 'sql', 'ddl'}
            returns = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
            if not returns:
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            if returns[-1].tool_name == 'read_task_progress':
                return ModelResponse(parts=[ToolCallPart('read_classroom_work', {'kind': 'exams'})])
            if returns[-1].tool_name == 'read_classroom_work':
                return ModelResponse(parts=[ToolCallPart(*selected[0])])
            seen.append(returns[-1].content)
            return ModelResponse(parts=[TextPart('下一步已准备，请核对后确认。')])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=sdk)
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    base = f'/api/workspaces/{auth[3]}'
    steps = [
        ('建立合成月考数学，满分100。', 'prepare_exam', {'title': '合成月考', 'subject': '数学', 'maximum_score': '100'}, 'exam.create'),
        ('录入合成月考数学合成学生0成绩80。', 'prepare_score', {'exam_title': '合成月考', 'subject': '数学', 'student_name': '合成学生0', 'status': 'scored', 'score': '80'}, 'score.record'),
        ('合成月考数学合成学生0更正为85，原因：合成核对。', 'prepare_score', {'exam_title': '合成月考', 'subject': '数学', 'student_name': '合成学生0', 'status': 'scored', 'score': '85', 'reason': '合成核对'}, 'score.record'),
        ('建立2排3座的座位表。', 'prepare_seat_layout', {'rows': 2, 'columns': 3}, 'seat.layout.create'),
        ('将合成学生0放在1排1座。', 'prepare_seat_assignment', {'student_name': '合成学生0', 'row': 1, 'column': 1}, 'seat.assign'),
        ('将合成学生1放在1排2座。', 'prepare_seat_assignment', {'student_name': '合成学生1', 'row': 1, 'column': 2}, 'seat.assign'),
        ('交换合成学生0与合成学生1的座位。', 'prepare_seat_swap', {'first_student': '合成学生0', 'second_student': '合成学生1'}, 'seat.swap'),
    ]
    thread = uuid4()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
        assert (await client.get(base + '/classroom-work/capabilities')).status_code == 200
        for message, tool, args, expected in steps:
            selected[0] = tool, args
            request = uuid4()
            prefix = base + f'/workspace-chat/threads/{thread}'
            sent = await client.post(prefix + '/turns', headers=headers, json={'request_id': str(request), 'text': message})
            assert sent.status_code == 200, sent.text
            stream = await client.post(prefix + f'/turns/{request}/events', headers=headers, json={})
            assert 'event: run.completed' in stream.text, (sdk.last_failure_type, stream.text)
            row = (await client.get(prefix)).json()['turns'][-1]
            assert row['candidate']['command'] == expected, (row, seen)
            assert row['action_receipt'] is None
            proposed = await client.post(prefix + f'/turns/{request}/proposal', headers=headers, json={'candidate_hash': row['candidate_hash']})
            assert proposed.status_code == 200, proposed.text
            value = proposed.json()
            approved = await client.post(base + '/commands/approve', headers=headers, json={'proposal_id': value['proposal_id'], 'payload_hash': value['payload_hash']})
            assert approved.status_code == 200, approved.text
            body = {'proposal_id': value['proposal_id'], 'idempotency_key': str(uuid4()), 'approval': approved.json()['approval']}
            result = await client.post(base + '/commands/commit', headers=headers, json=body)
            assert result.status_code == 200, result.text
            assert (await client.post(base + '/commands/commit', headers=headers, json=body)).json() == result.json()
            saved = (await client.get(prefix)).json()['turns'][-1]
            assert saved['action_receipt']['receipt_id'] == result.json()['receipt_id']
            assert (await client.post(prefix + f'/turns/{request}/events', headers=headers, json={})).text == ''
        exams = (await client.get(base + f'/classes/{c}/terms/{t}/exams')).json()['exams']
        assert len(exams) == 1
        scores = await client.get(base + f'/classes/{c}/terms/{t}/exams/{exams[0]["exam_id"]}')
        assert scores.status_code == 200 and scores.json()['average'] == '85.00'
        seating = await client.get(base + f'/classes/{c}/terms/{t}/seating')
        assert seating.status_code == 200, seating.text
        assert seating.json()['layout']['seats'][0]['student_id'] == str(students[1])
        # Agent names come from the fresh authorized roster, not UUID guessing
        # or assumptions about a previous seating plan in assistant history.
        from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
        capture = WorkspaceActionCapture(('查询座位',), classroom_enabled=True)
        read = next(tool for tool in capture.tools(query, auth, lambda: None, lambda *args, **kwargs: None)
                    if tool.__name__ == 'read_classroom_work')
        snapshot = await read('seating')
        assert [seat['student_name'] for seat in snapshot['layout']['seats']] == ['合成学生1', '合成学生0', None, None, None, None]
        # The legacy component proof remains valid after new pack read audits;
        # complete-world exit is still explicitly unavailable.
        assert (await client.get(base + '/workbench-d2/capabilities')).status_code == 200
        assert (await client.get(base + f'/classes/{uuid4()}/terms/{t}/exams')).status_code == 409
    # D4 pauses via the SDK immediately after candidate preparation; no extra
    # model response is needed before the original human preview/commit.
    assert seen == [] and sdk.active == 0
