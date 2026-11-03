"""Bounded read-only loopback health diagnostics; never repairs or mutates."""
import asyncio
import json
import httpx

from class_os.interfaces.http.contracts import LiveResponse, ReadyResponse
from class_os.interfaces.http.settings import Settings


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate health field")
        result[key] = value
    return result


async def _exchange(port, name):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2
    # One fresh client per probe: a health Set-Cookie cannot authorize the next
    # probe. No proxy/certificate environment, redirects, retry or body decoding.
    async with asyncio.timeout_at(deadline):
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=2) as client:
            async with client.stream('GET', f'http://127.0.0.1:{port}/health/{name}',
                                     headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'}) as response:
                raw = bytearray()
                async for chunk in response.aiter_raw(chunk_size=8193):
                    raw.extend(chunk)
                    if len(raw) > 8192:
                        break
                if loop.time() >= deadline:
                    raise TimeoutError()
                return response.status_code, bytes(raw)


async def _diagnose(settings):
    checks = {}
    for name, model in (("live", LiveResponse), ("ready", ReadyResponse)):
        try:
            status, raw = await _exchange(settings.port, name)
            if len(raw) > 8192 or status not in (200, 503):
                checks[name] = "invalid_response"
                continue
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
            if type(payload) is not dict or set(payload) != set(model.model_fields):
                raise ValueError("Incomplete health envelope")
            if name == "ready" and (type(payload["components"]) is not dict or set(payload["components"]) != {"database", "identity", "business_gateways"}):
                raise ValueError("Incomplete component evidence")
            value = model.model_validate(payload, strict=True)
            if name == "live":
                checks[name] = "ok" if status == 200 else "invalid_response"
            elif status == 200 and value.status == "ready" and set(value.components.model_dump().values()) == {"connected"}:
                checks[name] = "ok"
            elif status == 503 and value.status == "not_ready":
                checks[name] = "not_ready"
            else:
                checks[name] = "invalid_response"
        except (httpx.TransportError, OSError, TimeoutError):
            checks[name] = "unavailable"
        except (ValueError, TypeError, RecursionError):
            checks[name] = "invalid_response"
    ready = set(checks.values()) == {"ok"}
    return {"schema_version": "class-os.local-diagnostics.v1", "profile": "synthetic-development",
            "checks": checks, "ready": ready, "complete_operator_check": False,
            "next_step": "none" if ready else "start-local-api" if checks["live"] == "unavailable" else
            "check-owned-database-and-explicit-migration" if checks["ready"] == "not_ready" else "check-local-service-contract"}


def diagnose(settings):
    if type(settings) is not Settings:
        raise ValueError("Explicit synthetic Settings required")
    # Synchronous operator-only API; never run inside an HTTP request/Agent loop.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_diagnose(settings))
    raise ValueError("Local diagnostics require a synchronous operator context")
