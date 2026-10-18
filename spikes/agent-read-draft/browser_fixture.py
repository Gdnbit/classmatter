"""Disposable same-origin browser fixture. No real provider, identity or data."""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_ai import ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.models.function import FunctionModel
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from adapter import PydanticAIRuntime, RuntimeAuditSink
from boundary import EphemeralDraftBuilder, SyntheticQueryGateway, ToolGateway
from class_os_contracts import RouteMode
from transport import create_app

ROOT = Path(__file__).resolve().parent


def create_fixture(*, token: str, origin: str):
    models.ALLOW_MODEL_REQUESTS = False
    audit, drafts = RuntimeAuditSink(), EphemeralDraftBuilder()
    query = SyntheticQueryGateway({"synthetic-browser": {"as_of": "synthetic-time", "items": [
        {"id": "synthetic-1", "bucket": "NEEDS_ME", "title": "合成 🧪 中文",
         "source_ref": "synthetic-record@v1"},
    ]}})
    gateway = ToolGateway(query, drafts)
    model_counts = {"active": 0, "cleaned": 0}

    def factory(request):
        async def model(messages, info):
            if request.user_text in {"synthetic:cancel", "synthetic:timeout", "synthetic:slow"}:
                model_counts["active"] += 1
                try:
                    if request.user_text == "synthetic:slow":
                        await asyncio.sleep(0.7)
                        return ModelResponse(parts=[TextPart("合成 🧪 中文")])
                    await asyncio.Event().wait()
                finally:
                    model_counts["active"] -= 1
                    model_counts["cleaned"] += 1
            if request.user_text == "synthetic:ungrounded":
                return ModelResponse(parts=[TextPart("fabricated synthetic fact")])
            if len(messages) == 1:
                if request.route_mode == RouteMode.READ:
                    return ModelResponse(parts=[ToolCallPart("attention_list", {})])
                if request.route_mode == RouteMode.DRAFT_WRITE:
                    return ModelResponse(parts=[ToolCallPart("task_draft", {"title": "合成 🧪 中文草稿"})])
            return ModelResponse(parts=[TextPart("合成 🧪 中文")])
        return PydanticAIRuntime(FunctionModel(model), gateway, audit)

    app = create_app(factory, token=token, origin=origin, workspace_id="synthetic-browser")
    app.state.fixture_drafts = drafts
    expected_host = urlsplit(origin).netloc.encode("ascii")
    nonce = secrets.token_urlsafe(24)
    assets = {"client.mjs": ROOT / "browser/client.mjs", "runner.mjs": ROOT / "browser/runner.mjs"}
    for name in ("index.js", "parse.js", "errors.js"):
        assets[f"vendor/{name}"] = ROOT / "browser/node_modules/eventsource-parser/dist" / name

    def local(request):
        hosts = [v for k, v in request.scope["headers"] if k == b"host"]
        return (request.client is not None and request.client.host in {"127.0.0.1", "::1"}
                and hosts == [expected_host] and not request.scope["query_string"])

    async def page(request):
        if not local(request):
            return Response(status_code=403)
        html = (ROOT / "browser/index.html").read_text(encoding="utf-8")
        html = html.replace("__NONCE__", nonce).replace("__CONFIG__", json.dumps({"token": token}))
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "Content-Security-Policy":
                f"default-src 'none'; script-src 'self' 'nonce-{nonce}'; connect-src 'self'; "
                "style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})

    async def asset(request):
        path = assets.get(request.path_params["name"])
        if not local(request):
            return Response(status_code=403)
        if path is None or not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, media_type="text/javascript", headers={"Cache-Control": "no-store"})

    async def status(request):
        auth = [v for k, v in request.scope["headers"] if k == b"authorization"]
        if not local(request) or len(auth) != 1 or not hmac.compare_digest(auth[0], f"Bearer {token}".encode()):
            return Response(status_code=403)
        return JSONResponse({"synthetic_only": True, "active_streams": app.state.active_streams,
            "models": dict(model_counts), "business_writes": drafts.committed_business_writes,
            "outcomes": [{"run_id": r.correlation_id, "outcome": r.outcome} for r in audit.records]},
            headers={"Cache-Control": "no-store"})

    app.routes.extend([Route("/spike", page), Route("/spike/status", status),
                       Route("/spike/assets/{name:path}", asset)])
    return app


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("use an unprivileged loopback port")
    origin = f"http://127.0.0.1:{args.port}"
    print(f"Synthetic-only browser fixture: {origin}/spike", flush=True)
    uvicorn.run(create_fixture(token=secrets.token_urlsafe(32), origin=origin),
                host="127.0.0.1", port=args.port, proxy_headers=False, access_log=False,
                log_level="warning", timeout_graceful_shutdown=3)
