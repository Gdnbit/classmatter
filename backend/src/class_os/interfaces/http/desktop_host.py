"""Optional synthetic desktop process proof, not user or business authorization."""
import hashlib
import hmac
import re

from fastapi import Request
from starlette.responses import JSONResponse


def install_desktop_proof(app, key: str):
    if type(key) is not str or not re.fullmatch(r"[a-f0-9]{64}", key):
        raise ValueError("Invalid desktop process key")
    secret = bytes.fromhex(key)

    @app.get("/health/desktop")
    async def proof(request: Request):
        challenges = request.headers.getlist("x-classmatter-challenge")
        if len(challenges) != 1 or not re.fullmatch(r"[a-f0-9]{64}", challenges[0]):
            return JSONResponse({"error": "invalid_desktop_challenge"}, status_code=400)
        challenge = challenges[0]
        signed = hmac.new(secret, ("classmatter.desktop.v1:" + challenge).encode("ascii"), hashlib.sha256).hexdigest()
        return {"schema_version": "classmatter.desktop-proof.v1", "mode": "synthetic-only", "challenge": challenge, "proof": signed}
