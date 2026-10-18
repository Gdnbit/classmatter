"""Synthetic composition root. Health is not a business/query authority."""
import ipaddress
import json
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from class_os.application.audit import AuditUnavailable
from .contracts import ErrorDetail, ErrorResponse, LiveResponse, ReadyResponse
from .settings import Settings


def response_headers(request_id):
    return {"cache-control": "no-store", "x-content-type-options": "nosniff", "x-request-id": str(request_id)}


def rejection(status, code, request_id):
    body = ErrorResponse(request_id=request_id, error=ErrorDetail(code=code))
    return JSONResponse(body.model_dump(mode="json"), status_code=status, headers=response_headers(request_id))


class LocalBoundary:
    """Not authentication: reject proxy/public traffic before route dispatch."""

    def __init__(self, app, settings):
        self.app = app
        self.hosts = {f"127.0.0.1:{settings.port}".encode(), f"localhost:{settings.port}".encode()}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4()
        scope.setdefault("state", {})["request_id"] = request_id
        headers = scope.get("headers", [])
        hosts = [value for name, value in headers if name.lower() == b"host"]
        origins = [value for name, value in headers if name.lower() == b"origin"]
        try:
            peer = scope.get("client")
            local = bool(peer) and ipaddress.ip_address(peer[0]).is_loopback
        except ValueError:
            local = False
        forwarded = any(name.lower() == b"forwarded" or name.lower().startswith(b"x-forwarded-") for name, _ in headers)
        valid_host = len(hosts) == 1 and hosts[0] in self.hosts
        valid_origin = not origins or (len(origins) == 1 and valid_host and origins[0] == b"http://" + hosts[0])
        if not local or not valid_host or not valid_origin or forwarded:
            return await rejection(403, "local_boundary_rejected", request_id)(scope, receive, send)
        if scope.get("query_string"):
            return await rejection(400, "invalid_request", request_id)(scope, receive, send)

        if scope.get("path", "").startswith(("/api/identity/", "/api/workspaces/")) and scope.get("method") == "POST":
            # Bound credential requests before JSON/Pydantic parsing, including
            # chunked requests. Never reflect body fragments in an error.
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 8192:
                    return await rejection(400, "invalid_request", request_id)(scope, receive, send)
                if not message.get("more_body", False):
                    break

            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate JSON field")
                    result[key] = value
                return result

            try:
                if body:
                    json.loads(body, object_pairs_hook=unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeError, RecursionError):
                return await rejection(400, "invalid_request", request_id)(scope, receive, send)
            original_receive = receive
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if delivered:
                    return await original_receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            receive = buffered_receive

        response_started = False
        async def secured_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                protected = response_headers(request_id)
                message = dict(message)
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.decode().lower() not in protected]
                message["headers"] += [(k.encode(), v.encode()) for k, v in protected.items()]
            await send(message)

        try:
            await self.app(scope, receive, secured_send)
        except Exception:
            # ServerErrorMiddleware otherwise rethrows the original exception
            # after returning a safe 500, letting Uvicorn log DB rows/secrets.
            # Preserve a correlatable signal, never exception text or exc_info.
            logging.getLogger("class_os.api").error("request_failed code=internal_error request_id=%s", request_id)
            if response_started:
                # A partially sent response cannot become a second/successful
                # response. Only the static abort may reach the transport log.
                raise RuntimeError("HTTP response interrupted") from None
            await rejection(500, "internal_error", request_id)(scope, receive, secured_send)


def create_app(settings: Settings, *, identity=None, business=None, query=None, readiness=None, agent=None, model_controller=None):
    app = FastAPI(debug=False, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(LocalBoundary, settings=settings)

    if identity is not None:
        from .identity import router
        from class_os.application.identity import IdentityDenied, IdentityAlreadyCommitted
        app.include_router(router(identity))

        @app.exception_handler(IdentityDenied)
        async def identity_error(request: Request, exc: IdentityDenied):
            return rejection(401, "identity_rejected", request.state.request_id)

        @app.exception_handler(IdentityAlreadyCommitted)
        async def identity_duplicate(request: Request, exc: IdentityAlreadyCommitted):
            return rejection(409, "identity_already_committed", request.state.request_id)

    if business is not None or query is not None:
        if identity is None or business is None or query is None:
            raise ValueError("Business composition requires identity and both Gateways")
        from .roster import router as roster_router
        from class_os.application.roster import CommandRejected
        app.include_router(roster_router(business, query))
        from .model_configuration import router as configuration_router
        from class_os.application.model_configuration import ConfigurationRejected
        app.include_router(configuration_router(query, model_controller))

        @app.exception_handler(ConfigurationRejected)
        async def configuration_error(request: Request, exc: ConfigurationRejected):
            return rejection(400, "invalid_request", request.state.request_id)

        @app.exception_handler(CommandRejected)
        async def command_error(request: Request, exc: CommandRejected):
            return rejection(409, "business_rejected", request.state.request_id)

    if agent is not None:
        if identity is None or query is None:
            raise ValueError("Agent requires identity and Query Gateway")
        from .agent import router as agent_router
        from class_os.application.agent import AgentRejected
        app.include_router(agent_router(agent))

        @app.exception_handler(AgentRejected)
        async def agent_error(request: Request, exc: AgentRejected):
            return rejection(409, "business_rejected", request.state.request_id)

    @app.exception_handler(AuditUnavailable)
    async def audit_unavailable(request: Request, exc: AuditUnavailable):
        return rejection(503, "AUDIT_UNAVAILABLE", request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "invalid_request")
        return rejection(exc.status_code, code, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return rejection(400, "invalid_request", request.state.request_id)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return rejection(500, "internal_error", request.state.request_id)

    @app.get("/health/live", response_model=LiveResponse)
    async def live():
        return LiveResponse()

    @app.get("/health/ready", response_model=ReadyResponse, status_code=503)
    async def ready():
        if readiness is not None:
            try:
                readiness()
                body = ReadyResponse(status="ready", components={"database": "connected", "identity": "connected", "business_gateways": "connected"})
                return JSONResponse(body.model_dump(mode="json"), status_code=200)
            except Exception:
                # Composition exists but its complete readiness probe failed;
                # do not falsely say it was never configured or is connected.
                return ReadyResponse(components={"database": "unverified", "identity": "unverified", "business_gateways": "unverified"})
        return ReadyResponse()

    return app
