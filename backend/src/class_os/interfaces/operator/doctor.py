"""Bounded read-only loopback health diagnostics; never repairs or mutates."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from class_os.interfaces.http.contracts import LiveResponse, ReadyResponse
from class_os.interfaces.http.settings import Settings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate health field")
        result[key] = value
    return result


def diagnose(settings):
    if type(settings) is not Settings:
        raise ValueError("Explicit synthetic Settings required")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    checks = {}
    for name, model in (("live", LiveResponse), ("ready", ReadyResponse)):
        try:
            try:
                response = opener.open(Request(f"http://127.0.0.1:{settings.port}/health/{name}", headers={"Accept": "application/json"}), timeout=2)
            except HTTPError as error:
                response = error
            with response:
                status = response.code
                raw = response.read(8193)
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
        except (URLError, OSError, TimeoutError):
            checks[name] = "unavailable"
        except (ValueError, TypeError, RecursionError):
            checks[name] = "invalid_response"
    ready = set(checks.values()) == {"ok"}
    return {"schema_version": "class-os.local-diagnostics.v1", "profile": "synthetic-development",
            "checks": checks, "ready": ready, "complete_operator_check": False,
            "next_step": "none" if ready else "start-local-api" if checks["live"] == "unavailable" else
            "check-owned-database-and-explicit-migration" if checks["ready"] == "not_ready" else "check-local-service-contract"}
