"""Opt-in operator metadata. Never records prompts, exception bodies or credentials."""
import asyncio
import json
import socket
import ssl
import re
from time import monotonic

import httpx
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded


def classify_failure(error):
    """Describe observed boundaries, not an unproven vendor root cause."""
    chain, current = [], error
    for _ in range(8):
        if current is None or any(current is item for item in chain):
            break
        chain.append(current)
        current = current.__cause__ or current.__context__
    if isinstance(error, asyncio.CancelledError):
        return {"category": "cancelled"}
    for item in chain:
        for kind, category in ((httpx.ProxyError, "network_proxy"), (socket.gaierror, "network_dns"),
                               (ssl.SSLError, "network_tls"), (httpx.ConnectTimeout, "network_connect_timeout"),
                               (httpx.ReadTimeout, "network_read_timeout"), (httpx.WriteTimeout, "network_write_timeout"),
                               (httpx.PoolTimeout, "local_connection_pool"), (httpx.ConnectError, "network_connect"),
                               (httpx.ReadError, "network_read"), (httpx.WriteError, "network_write"),
                               (httpx.RemoteProtocolError, "network_protocol")):
            if isinstance(item, kind):
                # More precise DNS/TLS causes take precedence over ConnectError wrappers.
                if kind is httpx.ConnectError and any(isinstance(cause, (socket.gaierror, ssl.SSLError)) for cause in chain):
                    continue
                return {"category": category}
    for item in chain:
        if isinstance(item, ModelHTTPError):
            status = item.status_code
            body = item.body
            if isinstance(body, str) and len(body) <= 16384:
                try:
                    body = json.loads(body)
                except (ValueError, RecursionError):
                    body = None
            envelope = body.get("error", body) if isinstance(body, dict) else None
            signal = envelope.get("status") if isinstance(envelope, dict) else None
            known = ("UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED", "INTERNAL",
                     "INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED", "NOT_FOUND")
            result = {"category": "upstream_rate_limit" if status == 429 else "upstream_http", "http_status": status}
            if signal in known:
                result["provider_status"] = signal
            return result
    if isinstance(error, UsageLimitExceeded):
        result = {"category": "local_usage_limit"}
        # Emit only a known SDK limit name, never the exception text/counts.
        detail = str(error)[:1024]
        for limit in ('request_limit', 'tool_calls_limit', 'input_tokens_limit', 'output_tokens_limit', 'total_tokens_limit'):
            if re.search(r'\b' + limit + r'\b', detail):
                result['limit'] = limit
                break
        return result
    if isinstance(error, TimeoutError):
        return {"category": "timeout_unattributed"}
    if isinstance(error, UnexpectedModelBehavior):
        return {"category": "model_contract"}
    return {"category": "unclassified"}


class RunDiagnostics(AbstractCapability):
    """One instance per run; a broken observer cannot change the result."""
    id = "operator-run-diagnostics"

    def __init__(self, sink, run_id):
        self.sink, self.run_id = sink, str(run_id)
        self.started, self.requests, self.model_ms = monotonic(), 0, 0
        self.request_failure = None
        self.steps = []

    async def wrap_model_request(self, ctx, *, request_context, handler):
        self.requests += 1
        started = monotonic()
        outcome = 'completed'
        try:
            return await handler(request_context)
        except BaseException as error:
            self.request_failure = classify_failure(error)
            outcome = self.request_failure['category']
            raise
        finally:
            elapsed = int((monotonic() - started) * 1000)
            self.model_ms += elapsed
            if len(self.steps) < 10:
                self.steps.append({'request': self.requests, 'ms': elapsed, 'outcome': outcome})

    def finish(self, outcome, error=None, *, phase="model_loop", tool_calls=0, deadline_expired=False):
        packet = {"run_id": self.run_id, "outcome": outcome, "model_requests": self.requests,
                  "model_ms": self.model_ms, "elapsed_ms": int((monotonic() - self.started) * 1000),
                  "phase": phase, "tool_calls": tool_calls, "model_steps": [dict(step) for step in self.steps]}
        if error is not None:
            packet.update(classify_failure(error))
            if deadline_expired:
                packet['category'] = 'local_run_deadline'
            if self.request_failure is not None:
                packet["model_failure"] = dict(self.request_failure)
        if self.sink is not None:
            try:
                self.sink(packet)
            except Exception:
                pass  # Diagnostics is neither a business write nor a success gate.
