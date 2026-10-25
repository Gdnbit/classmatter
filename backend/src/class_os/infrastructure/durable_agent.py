"""Opt-in chat orchestration; original Pydantic AI still owns every model loop.

Not registered in HTTP/UI. Read/draft history requires typed source/card storage
before activation. No model receives this server-owned BCG handle.
"""
from contextlib import aclosing, suppress
from time import monotonic

import anyio
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

from class_os.application.agent import AgentRequest, AgentRejected, Mode, RuntimeEvent
from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.application.conversation_interaction import ConversationInteractionQuery
from .agent import PydanticAgentRuntime


class DurableChatRuntime:
    def __init__(self, worker, query, runtime):
        if (type(worker) is not ConversationWorkerGateway or type(query) is not ConversationInteractionQuery
                or type(runtime) is not PydanticAgentRuntime or runtime.query is not query
                or worker.store is not query.store or worker.identity is not query.identity):
            raise ValueError("Exact scoped D1 composition required")
        self.worker, self.query, self.runtime = worker, query, runtime

    async def stream(self, credentials, class_id, term_id, thread_id, request_id, text):
        # Enqueue is human input, not model output or an Agent write tool.
        await anyio.to_thread.run_sync(lambda: self.worker.enqueue(*credentials, class_id, term_id, thread_id, request_id, text, "chat"))
        ticket = await anyio.to_thread.run_sync(lambda: self.worker.claim(credentials, class_id, term_id, thread_id, request_id))
        if ticket is None:
            return  # Caller reads QG status/history; never automatic redispatch.
        conversation, settled, cursor = None, False, 0
        started = monotonic()

        def event(kind, payload):
            nonlocal cursor
            cursor += 1
            return RuntimeEvent(cursor, ticket.run.run_id, kind, payload)

        async def finish(state, output=None):
            await anyio.to_thread.run_sync(lambda: self.worker.finish_run(credentials, ticket, state, output,
                duration_ms=min(2147483647, int((monotonic() - started) * 1000))))

        try:
            if ticket.intent.mode != "chat" or ticket.scope.student_id is not None:
                raise AgentRejected()
            history = await anyio.to_thread.run_sync(lambda: self.query.conversation_history(*credentials, class_id, term_id, thread_id))
            conversation = await anyio.to_thread.run_sync(lambda: self.runtime.conversation(credentials))
            if conversation.class_id != class_id or conversation.term_id != term_id:
                raise AgentRejected()
            # Only bounded visible text, never SDK tool/approval/credential dumps.
            # Original SDK instructions treat history as untrusted, not current facts.
            messages = [item for item in history.history.messages if item.turn_id != ticket.turn_id][-10:]
            conversation.history = [ModelRequest(parts=[UserPromptPart(item.content.text)]) if item.content.role == "user"
                                    else ModelResponse(parts=[TextPart(item.content.text)]) for item in messages]
            pending, completed = [], False
            request = AgentRequest(conversation.conversation_id, ticket.intent.text, Mode.CHAT)
            current = await anyio.to_thread.run_sync(lambda: self.query.turn_status(*credentials, class_id, term_id, thread_id, request_id))
            if (current["run_id"] != ticket.run.run_id or current["state"] != "running"
                    or current["version"] != ticket.run.version or self.worker.clock() >= ticket.run.lease_until):
                raise AgentRejected()
            async with aclosing(self.runtime.stream(credentials, request)) as stream:
                async for item in stream:
                    if item.type in ("message.delta", "run.completed"):
                        pending.append(item)
                        completed = item.type == "run.completed" or completed
                    elif item.type == "run.failed":
                        break
                    elif item.type == "draft.available":
                        raise AgentRejected()  # No unversioned structured draft history.
                    else:
                        yield event(item.type, item.payload)
            answers = [item for item in pending if item.type == "message.delta"]
            if not completed or len(answers) != 1 or answers[0].payload.get("source_refs"):
                await finish("unknown")
                settled = True
                yield event("run.failed", {"code": "agent_unavailable"})
                return
            await finish("completed", answers[0].payload["text"])
            settled = True
            # Persistence + trusted audit committed before either answer/completion.
            for item in pending:
                current = await anyio.to_thread.run_sync(lambda: self.query.conversation_history(*credentials, class_id, term_id, thread_id))
                visible = [message for message in current.history.messages if message.turn_id == ticket.turn_id
                           and message.content.role == "assistant" and message.content.text == answers[0].payload["text"]]
                if current.history.status != "active" or len(visible) != 1:
                    raise AgentRejected()
                yield event(item.type, item.payload)
        except Exception:
            yield event("run.failed", {"code": "persistence_or_run_unknown"})
        finally:
            if not settled:
                # Local abort/provider uncertainty is not proof of zero provider cost.
                # Expired identity/lease may deny this; authorized reconcile then fences it.
                with anyio.CancelScope(shield=True):
                    with suppress(Exception):
                        await finish("unknown")
            if conversation is not None:
                conversation.history.clear()
                with suppress(AgentRejected):
                    self.runtime.memory.forget(credentials, conversation.conversation_id)
