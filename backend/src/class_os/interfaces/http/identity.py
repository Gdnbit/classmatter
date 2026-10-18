"""Cookie transport for the ISB; no database access or business authority."""
import hmac
import re
import secrets
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.responses import JSONResponse

from .identity_contracts import COOKIE_SECRET, IdentityChallenge, IdentitySession, IdentityKitSession, IdentitySignedOut
from .identity_contracts import IdentityLogoutBody, IdentityLogoutReceipt
from .identity_contracts import IdentityAction, IdentityOperationReceipt


class PasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=16, max_length=256)
    request_id: UUID | None = None


class BootstrapBody(PasswordBody):
    secret: SecretStr = Field(min_length=32, max_length=128)


class RecoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=32, max_length=160)
    request_id: UUID | None = None


def cookie(response, name, value, *, recovery=False, age=3600):
    # HTTP is permitted only by the loopback synthetic composition. A production
    # HTTPS deployment must supply a separate reviewed secure-cookie policy.
    checked = COOKIE_SECRET.validate_python(value)
    response.set_cookie("class_os_" + name, checked, httponly=True, samesite="strict",
                        secure=False, path="/api/identity/recovery" if recovery else "/api", max_age=age)


def value(request, name):
    return request.cookies.get("class_os_" + name, "")


def mutation(request, csrf_name):
    expected = value(request, csrf_name)
    actual = request.headers.get("x-class-os-csrf", "")
    if (request.headers.get("origin") != "http://" + request.headers.get("host", "")
            or not 32 <= len(expected) <= 128 or not 32 <= len(actual) <= 128
            or not hmac.compare_digest(expected, actual)):
        raise HTTPException(403)
    return actual


def identity_json(model, payload):
    return JSONResponse(model.model_validate(payload).model_dump(mode="json"))


def session_response(result, *, recovery=False, require_kit=False):
    body = {"schema_version": "class-os.identity.v1", "csrf_token": result.csrf}
    if not recovery:
        body["subject"] = {"owner_id": str(result.subject.owner_id), "workspace_id": str(result.subject.workspace_id)}
    if result.recovery_codes:
        body["recovery_codes"] = list(result.recovery_codes)
    model = IdentityChallenge if recovery else IdentityKitSession if require_kit else IdentitySession
    response = identity_json(model, body)
    cookie(response, "recovery" if recovery else "session", result.token, recovery=recovery, age=600 if recovery else 3600)
    cookie(response, "recovery_csrf" if recovery else "csrf", result.csrf, recovery=recovery, age=600 if recovery else 3600)
    return response


def router(boundary):
    routes = APIRouter(prefix="/api/identity")

    def invoke(request, body, action, csrf, callback, *, token_name="session"):
        if body.request_id is None:
            return callback()  # Existing v1 clients; no replay promise without an ID.
        token = value(request, token_name) if token_name else None
        with boundary.operation(action, body.request_id, value(request, "client"), csrf, token):
            return callback()

    @routes.get("/receipts/{action}/{request_id}")
    def operation_receipt(action: IdentityAction, request_id: UUID, request: Request):
        csrf = request.headers.get("x-class-os-csrf", "")
        if not csrf:
            raise HTTPException(403)
        status = boundary.operation_status(action, request_id, value(request, "client"), csrf)
        return identity_json(IdentityOperationReceipt, {"schema_version": "class-os.identity-operation-receipt.v1",
            "request_id": str(request_id), "action": action, "status": status, "result_replayable": False})

    @routes.get("/context")
    def context(request: Request):
        client = value(request, "client")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", client):
            client = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        response = identity_json(IdentityChallenge, {"schema_version": "class-os.identity.v1", "csrf_token": csrf})
        cookie(response, "client", client)
        cookie(response, "pre_csrf", csrf, age=600)
        return response

    @routes.post("/bootstrap")
    def bootstrap(request: Request, body: BootstrapBody):
        csrf = mutation(request, "pre_csrf")
        result = invoke(request, body, "bootstrap", csrf,
            lambda: boundary.bootstrap(body.secret.get_secret_value(), body.password.get_secret_value(), value(request, "client")), token_name=None)
        return session_response(result, require_kit=True)

    @routes.post("/login")
    def login(request: Request, body: PasswordBody):
        csrf = mutation(request, "pre_csrf")
        result = invoke(request, body, "login", csrf,
            lambda: boundary.login(body.password.get_secret_value(), value(request, "client")), token_name=None)
        return session_response(result)

    @routes.get("/session")
    def session(request: Request):
        csrf = value(request, "csrf")
        subject = boundary.authenticate(value(request, "session"), value(request, "client"), csrf)
        return identity_json(IdentitySession, {"schema_version": "class-os.identity.v1", "csrf_token": csrf,
                "subject": {"owner_id": str(subject.owner_id), "workspace_id": str(subject.workspace_id)}})

    @routes.post("/logout")
    def logout(request: Request, body: IdentityLogoutBody | None = None):
        csrf = mutation(request, "csrf")
        if body is None or body.request_id is None:
            boundary.logout(value(request, "session"), value(request, "client"), csrf)
        else:
            boundary.logout(value(request, "session"), value(request, "client"), csrf, body.request_id)
        response = identity_json(IdentitySignedOut, {"schema_version": "class-os.identity.v1", "status": "signed_out"})
        for name in ("session", "csrf"):
            response.delete_cookie("class_os_" + name, path="/api", httponly=True, samesite="strict")
        return response

    @routes.get("/logout/receipts/{request_id}")
    def logout_receipt(request_id: UUID, request: Request):
        csrf = request.headers.get("x-class-os-csrf", "")
        if not csrf:
            raise HTTPException(403)
        status = boundary.logout_status(request_id, value(request, "client"), csrf)
        return identity_json(IdentityLogoutReceipt, {"schema_version": "class-os.identity-logout-receipt.v1",
            "request_id": str(request_id), "action": "logout", "status": status})

    @routes.post("/reauthenticate")
    def reauthenticate(request: Request, body: PasswordBody):
        csrf = mutation(request, "csrf")
        result = invoke(request, body, "reauthenticate", csrf,
            lambda: boundary.reauthenticate(value(request, "session"), value(request, "client"), csrf, body.password.get_secret_value()))
        return session_response(result)

    @routes.post("/logout-all")
    def logout_all(request: Request, body: PasswordBody):
        csrf = mutation(request, "csrf")
        invoke(request, body, "logout_all", csrf,
            lambda: boundary.logout_all(value(request, "session"), value(request, "client"), csrf, body.password.get_secret_value()))
        response = identity_json(IdentitySignedOut, {"schema_version": "class-os.identity.v1", "status": "signed_out_all"})
        for name in ("session", "csrf"):
            response.delete_cookie("class_os_" + name, path="/api", httponly=True, samesite="strict")
        return response

    @routes.post("/recovery/reissue")
    def reissue(request: Request, body: PasswordBody):
        csrf = mutation(request, "csrf")
        result = invoke(request, body, "recovery_reissue", csrf,
            lambda: boundary.reissue_recovery(value(request, "session"), value(request, "client"), csrf, body.password.get_secret_value()))
        return session_response(result, require_kit=True)

    @routes.post("/recovery/exchange")
    def exchange(request: Request, body: RecoveryBody):
        csrf = mutation(request, "pre_csrf")
        result = invoke(request, body, "recovery_exchange", csrf,
            lambda: boundary.exchange_recovery(body.code.get_secret_value(), value(request, "client")), token_name=None)
        return session_response(result, recovery=True)

    @routes.post("/recovery/complete")
    def complete(request: Request, body: PasswordBody):
        csrf = mutation(request, "recovery_csrf")
        result = invoke(request, body, "recovery_complete", csrf,
            lambda: boundary.complete_recovery(value(request, "recovery"), value(request, "client"), csrf, body.password.get_secret_value()), token_name="recovery")
        response = session_response(result, require_kit=True)
        for name in ("recovery", "recovery_csrf"):
            response.delete_cookie("class_os_" + name, path="/api/identity/recovery", httponly=True, samesite="strict")
        return response

    return routes
