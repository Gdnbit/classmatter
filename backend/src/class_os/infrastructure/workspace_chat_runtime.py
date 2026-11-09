"""Persist-before-dispatch/release orchestration around the existing SDK loop."""
import asyncio
from contextlib import aclosing, suppress
from time import monotonic

import anyio
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

from class_os.application.agent import AgentRequest, AgentRejected, Mode, RuntimeEvent
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from .agent import PydanticAgentRuntime
from .workspace_actions import WorkspaceActionCapture


class WorkspaceChatRuntime:
    def __init__(self, business, query, sdk):
        if (type(business) is not WorkspaceChatBusinessGateway or type(query) is not WorkspaceChatQueryGateway
                or type(sdk) is not PydanticAgentRuntime or business.store is not query.store
                or sdk.query.store is not business.store or business.identity is not query.identity or sdk.query.identity is not business.identity
                or business.store.database.profile != "workspace-chat-d3"):
            raise ValueError("Exact workspace chat composition required")
        self.business, self.query, self.sdk = business, query, sdk

    async def stream_queued(self, credentials, thread_id, request_id):
        ticket = await anyio.to_thread.run_sync(lambda: self.business.claim(credentials, thread_id, request_id))
        if ticket is None:
            return  # GET/reconnect/repeated start never redispatches.
        started, conversation, capture, settled, cursor = monotonic(), None, None, False, 0

        def event(kind, payload):
            nonlocal cursor
            cursor += 1
            return RuntimeEvent(cursor, ticket["turn_id"], kind, payload)

        async def finish(state, answer=None, proposed=None):
            return await anyio.to_thread.run_sync(lambda: self.business.finish(credentials, ticket, state, answer, proposed,
                duration_ms=min(2147483647, int((monotonic() - started) * 1000)),
                input_tokens=capture.input_tokens if capture else None, output_tokens=capture.output_tokens if capture else None))

        try:
            history = await anyio.to_thread.run_sync(lambda: self.query.history(credentials, thread_id))
            current = next((row for row in history["turns"] if row["request_id"] == request_id), None)
            if current is None or current["state"] != "running" or current["version"] != ticket["version"]:
                raise AgentRejected()
            conversation = await anyio.to_thread.run_sync(lambda: self.sdk.workspace_conversation(credentials))
            previous, total = [], 0
            for row in reversed([row for row in history["turns"] if row["ordinal"] < ticket["ordinal"] and row["state"] == "completed"]):
                size = len(row["user_text"]) + len(row["assistant_text"])
                if len(previous) >= 6 or total + size > 8000:
                    break
                previous.insert(0, row); total += size
            conversation.history = [message for row in previous for message in (
                ModelRequest(parts=[UserPromptPart(row["user_text"])]), ModelResponse(parts=[TextPart(row["assistant_text"])]))]
            capture = WorkspaceActionCapture(tuple([row["user_text"] for row in previous] + [ticket["user_text"]]),
                progress_reader=lambda: self.query.history(credentials, thread_id))
            pending, completed = [], False
            request = AgentRequest(conversation.conversation_id, ticket["user_text"], Mode.CHAT)
            async with aclosing(self.sdk.stream(credentials, request, _workspace_actions=capture)) as stream:
                async for item in stream:
                    if item.type in ("message.delta", "draft.available", "run.completed"):
                        pending.append(item); completed = completed or item.type == "run.completed"
                    elif item.type == "run.failed":
                        break
                    else:
                        yield event(item.type, item.payload)
            answers = [item.payload["text"] for item in pending if item.type == "message.delta"]
            if not completed or len(answers) != 1:
                await finish("failed"); settled = True
                yield event("run.failed", {"code": "agent_unavailable"}); return
            stored = await finish("completed", answers[0], capture.proposed)
            settled = True
            if stored["state"] != "completed":
                yield event("run.failed", {"code": "run_expired"}); return
            # User-visible success is released only after BCG output and audit commit.
            for item in pending:
                yield event(item.type, item.payload)
        except asyncio.CancelledError:
            with suppress(Exception):
                await finish("cancelled")
            settled = True
            raise
        except Exception:
            with suppress(Exception):
                await finish("unknown"); settled = True
            yield event("run.failed", {"code": "run_unavailable"})
        finally:
            if not settled:
                with suppress(Exception):
                    await finish("unknown")
            if conversation is not None:
                with suppress(Exception):
                    self.sdk.memory.forget(credentials, conversation.conversation_id)
