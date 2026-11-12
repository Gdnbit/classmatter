"""SIM-03: the Agent sees actual deadlines, not only titles/statuses."""
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.agent import AgentRequest, Mode
from class_os.domain.activity import CreateTask
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.db
async def test_chat_task_query_preserves_deadline_and_unknown_without_writes(roster):
    gateway, query, _, credentials, _, owner, clock = roster
    classroom, _, _ = seed(roster)
    due = clock[0] + timedelta(days=1)
    for title, deadline in [('合成有期限任务', due), ('合成未设期限任务', None)]:
        submit(gateway, credentials, CreateTask('task.create', uuid4(), classroom.class_id, classroom.term_id, title, deadline))
    observed = []
    def factory(request):
        def respond(messages, info):
            returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
            if not returned:
                return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'tasks'})])
            observed.extend(returned[-1].content['items'])
            return ModelResponse(parts=[TextPart('已查询当前任务及截止时间。')])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    conversation = sdk.workspace_conversation(credentials)
    capture = WorkspaceActionCapture(('查询当前任务和截止时间。',))
    events = [event async for event in sdk.stream(credentials,
        AgentRequest(conversation.conversation_id, '查询当前任务和截止时间。', Mode.CHAT), _workspace_actions=capture)]
    assert events[-1].type == 'run.completed'
    by_title = {row['title']: row for row in observed}
    assert by_title['合成有期限任务']['due_at'] == due.isoformat()
    assert by_title['合成未设期限任务']['due_at'] is None
    assert capture.proposed is None
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.manual_task')).scalar_one() == 2
        assert connection.execute(text('SELECT max(version) FROM class_os.manual_task')).scalar_one() == 1
