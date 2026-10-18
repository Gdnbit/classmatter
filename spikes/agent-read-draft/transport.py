"""Loopback synthetic ASGI transport, never a production auth/API boundary."""

from __future__ import annotations

import asyncio
import hmac
import json
from collections.abc import Callable
from contextlib import aclosing
from dataclasses import asdict
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from class_os_contracts import AgentRuntimePort, RouteMode, RuntimeRequest


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    user_text: str = Field(min_length=1, max_length=8000)
    route_mode: str


class InputError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON key")
        result[key] = value
    return result


class OwnedStreamingResponse(StreamingResponse):
    """Starlette owns wire semantics; this adapter owns iterator/slot lifetime."""

    def __init__(self, content, release):
        super().__init__(content, media_type="text/event-stream", headers={
            "Cache-Control": "no-store", "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        })
        self.release = release

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        except ClientDisconnect:
            pass
        finally:
            try:
                # The response iterator may be suspended at yield when socket send
                # fails. Close explicitly, including under AnyIO disconnect cancel.
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()
            finally:
                self.release()


def create_app(
    runtime_factory: Callable[[RuntimeRequest], AgentRuntimePort], *, token: str,
    origin: str, workspace_id: str,
) -> Starlette:
    parsed = urlsplit(origin)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or not parsed.port or len(token) < 24 or not workspace_id.startswith("synthetic")):
        raise ValueError("transport requires a loopback synthetic fixture configuration")
    expected_origin, expected_host = origin.encode("ascii"), parsed.netloc.encode("ascii")
    expected_auth = f"Bearer {token}".encode("ascii")

    def error(code, status):
        return JSONResponse({"error": code}, status_code=status, headers={"Cache-Control": "no-store"})

    async def events(request: Request):
        headers = request.scope["headers"]

        def exactly_one(name, expected):
            values = [value for key, value in headers if key == name]
            return len(values) == 1 and hmac.compare_digest(values[0], expected)

        if (request.client is None or request.client.host not in {"127.0.0.1", "::1"}
                or not exactly_one(b"host", expected_host)
                or not exactly_one(b"origin", expected_origin)
                or not exactly_one(b"authorization", expected_auth)):
            return error("forbidden", 403)
        if request.scope["query_string"]:
            return error("query_not_supported", 400)
        if any(key == b"last-event-id" for key, _ in headers):
            return error("replay_not_supported", 409)
        content_types = [value for key, value in headers if key == b"content-type"]
        if len(content_types) != 1 or content_types[0].split(b";", 1)[0] != b"application/json":
            return error("json_required", 415)
        if app.state.active_streams >= 4:
            return error("capacity_exceeded", 429)
        app.state.active_streams += 1
        owned = False
        try:
            body = bytearray()
            async with asyncio.timeout(1):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 16384:
                        return error("request_too_large", 413)
                    body.extend(chunk)
            data = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
            turn = Turn.model_validate(data)
            if not turn.user_text.strip():
                raise InputError("blank text")
            route = RouteMode(turn.route_mode)
            tools = {RouteMode.READ: frozenset({"attention.list"}),
                     RouteMode.DRAFT_WRITE: frozenset({"task.draft"})}.get(route, frozenset())
            runtime_request = RuntimeRequest(
                uuid4().hex, uuid4().hex, uuid4().hex, workspace_id,
                turn.user_text, route, tools,
            )
            runtime = runtime_factory(runtime_request)

            async def wire():
                async with aclosing(runtime.stream(runtime_request)) as stream:
                    async for event in stream:
                        envelope = json.dumps(asdict(event), ensure_ascii=False, allow_nan=False)
                        yield f"id: {event.cursor}\nevent: {event.type}\ndata: {envelope}\n\n"

            def release():
                app.state.active_streams -= 1

            response = OwnedStreamingResponse(wire(), release)
            owned = True
            return response
        except TimeoutError:
            return error("request_timeout", 408)
        except ClientDisconnect:
            return error("request_disconnected", 400)
        except (ValueError, ValidationError, RecursionError):
            return error("invalid_request", 400)
        finally:
            if not owned:
                app.state.active_streams -= 1

    app = Starlette(routes=[Route("/spike/events", events, methods=["POST"])])
    app.state.active_streams = 0
    return app
