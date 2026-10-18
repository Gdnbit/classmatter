import io
import logging
import socket
from threading import Thread
import time
import traceback

import httpx
import pytest
from starlette.responses import StreamingResponse
import uvicorn

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings


def test_real_tcp_internal_fault_never_rethrows_raw_detail_to_uvicorn(caplog):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(Settings(port=port))
    @app.get("/test-only-fault")
    def fault():
        raise RuntimeError("synthetic-private-exception-detail")
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    logger = logging.getLogger("uvicorn.error")
    logger.addHandler(handler)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False,
                                          proxy_headers=False, log_config=None, log_level="error"))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        with httpx.Client(trust_env=False) as client:
            result = client.get(f"http://127.0.0.1:{port}/test-only-fault")
        assert result.status_code == 500
        assert result.json()["error"]["code"] == "internal_error"
        assert result.json()["request_id"] == result.headers["x-request-id"]
        assert "synthetic-private-exception-detail" not in result.text
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        logger.removeHandler(handler)
        assert not thread.is_alive()
    assert "synthetic-private-exception-detail" not in output.getvalue()
    assert "synthetic-private-exception-detail" not in caplog.text
    assert f"request_id={result.headers['x-request-id']}" in caplog.text
    assert any(record.name == "class_os.api" and record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_started_response_fault_is_static_abort_not_success(caplog):
    app = create_app(Settings())
    @app.get("/test-only-stream-fault")
    async def stream():
        async def chunks():
            yield b"synthetic-safe-prefix"
            raise RuntimeError("synthetic-private-stream-detail")
        return StreamingResponse(chunks())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345), raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        with pytest.raises(RuntimeError) as failure:
            await client.get("/test-only-stream-fault")
    rendered = "".join(traceback.format_exception(failure.value))
    assert "synthetic-private-stream-detail" not in rendered
    assert "synthetic-private-stream-detail" not in caplog.text
