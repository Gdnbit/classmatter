"""Local candidate capture and at-most-once submission; no application DB calls."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from typing import Callable

from .model import ConnectorError, Message, Page, PRESETS, Scope, digest, label


def read_json(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_size > 64_000_000:
        raise ConnectorError("invalid_local_state")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConnectorError("invalid_local_state")
    return value


def atomic_json(path: Path, value: dict):
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > 64_000_000:
        raise ConnectorError("candidate_byte_limit_reached")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def desktop_lock():
    """Serialize our connectors across runtimes/processes, not other desktop software.

    A crash leaves the lock. An operator must check that the old worker is stopped
    before removing it; guessing about a timed-out send is deliberately forbidden.
    """
    path = Path(tempfile.gettempdir()) / "classmatter-wechat-desktop.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ConnectorError("desktop_busy_or_recovery_required") from None
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def restart_capture(root: Path, scope: Scope):
    """Explicit rescan preserves previous evidence; never deletes old candidates."""
    path = root / (scope.key + ".candidate.json")
    if path.exists():
        if path.is_symlink():
            raise ConnectorError("invalid_local_state")
        path.rename(root / (scope.key + ".previous-" + uuid.uuid4().hex + ".json"))


def capture(root: Path, scope: Scope, read: Callable[[int, int], Page], *,
            page_size: int = 100, max_messages: int = 1000,
            cancelled: Callable[[], bool] = lambda: False) -> dict:
    if type(page_size) is not int or not 1 <= page_size <= 500:
        raise ConnectorError("invalid_limit")
    if type(max_messages) is not int or not 1 <= max_messages <= 100_000:
        raise ConnectorError("invalid_limit")
    path = root / (scope.key + ".candidate.json")
    state = read_json(path) if path.exists() else {
        "schema": "wechat-capture-candidate-v1", "scope": asdict(scope),
        "messages": [], "source_exhausted": None, "complete": False,
        "coverage": PRESETS[scope.provider]["history"], "status": "pending",
        "business_fact": False, "attachments": "metadata-only",
        "consistency": "source-observation-not-atomic-snapshot",
        "account_binding_verified": False,
    }
    if (state.get("schema") != "wechat-capture-candidate-v1"
            or state.get("scope") != asdict(scope) or state.get("business_fact") is not False
            or not isinstance(state.get("messages"), list)):
        raise ConnectorError("invalid_local_state")
    existing = [asdict(Message(**m)) for m in state["messages"]]
    # UI reads are observations, not stable paginated snapshots. Each invocation
    # replaces that observation rather than claiming historical merge completeness.
    if scope.provider != "replica":
        if cancelled():
            raise ConnectorError("cancelled")
        page = read(min(max_messages, 500), 0)
        state.update(messages=[asdict(m) for m in page.messages], coverage=page.coverage,
                     status="observed", source_exhausted=None, complete=False)
        atomic_json(path, state)
        return state
    state["complete"] = False
    state["source_exhausted"] = None
    while True:
        if cancelled():
            state["status"] = "cancelled"
            atomic_json(path, state)
            return state
        # Revalidate the WHOLE previously captured prefix, not only its first row:
        # new messages, edits, deletions and reordered shard ties invalidate resume.
        size = min(page_size, max_messages - len(existing))
        if size <= 0:
            state["status"] = "limit-reached"
            atomic_json(path, state)
            return state
        fresh: list[dict] = []
        exhausted = False
        target = len(existing) + size
        for offset in range(0, target, page_size):
            if cancelled():
                state["status"] = "cancelled"
                atomic_json(path, state)
                return state
            page = read(min(page_size, target - offset), offset)
            if len(page.messages) > min(page_size, target - offset):
                raise ConnectorError("upstream_contract_changed")
            if not page.messages and page.exhausted is not True:
                raise ConnectorError("source_not_progressing")
            if page.coverage != "paginated-local":
                raise ConnectorError("upstream_contract_changed")
            fresh.extend(asdict(m) for m in page.messages)
            if page.exhausted is True:
                exhausted = True
                break
        if fresh[:len(existing)] != existing:
            state.update(status="source-changed-restart-required", complete=False,
                         source_exhausted=None)
            atomic_json(path, state)
            raise ConnectorError("source_changed")
        ids = [m["source_id"] for m in fresh]
        if len(set(ids)) != len(ids):
            raise ConnectorError("duplicate_native_identity")
        # An empty tail is meaningful only after the prefix was revalidated.
        existing = fresh
        state.update(messages=existing, source_exhausted=exhausted, complete=False,
                     status="source-exhausted" if exhausted else "partial",
                     coverage="paginated-local", captured_at=int(time.time()))
        atomic_json(path, state)
        if exhausted:
            return state


def approval(scope: Scope, text: str, request_id: str) -> str:
    label(request_id, 128)
    if not isinstance(text, str) or not text.strip() or len(text) > 2000 or "\x00" in text:
        raise ConnectorError("invalid_message")
    return digest([asdict(scope), text, request_id])


def submit(root: Path, scope: Scope, text: str, request_id: str,
           approved_hash: str, send: Callable[[str], str]) -> dict:
    expected = approval(scope, text, request_id)
    if expected != approved_hash:
        raise ConnectorError("approval_mismatch")
    if not PRESETS[scope.provider]["send"]:
        raise ConnectorError("send_not_supported")
    # Provider-independent key prevents retry through a different connector.
    key = digest([scope.account, scope.chat, request_id])
    path = root / (key + ".outbound.json")
    result = {"schema": "wechat-outbound-v1", "request": key, "approval": expected,
              "provider": scope.provider, "status": "unknown", "retry_allowed": False}
    # Claim BEFORE the external side effect. A crash/timeout leaves unknown, not retryable.
    root.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ConnectorError("already_attempted_manual_reconciliation_required") from None
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(result, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        status = send(text)
        if status == "submitted-unconfirmed":
            result["status"] = status
    except Exception:
        # Do not expose upstream logs, credentials or chat content; no fallback/retry.
        pass
    atomic_json(path, result)
    return result


def claim_dispatch(root: Path, scope: Scope, text: str, request_id: str):
    """The isolated worker cannot submit without the parent's durable preview claim."""
    expected = approval(scope, text, request_id)
    key = digest([scope.account, scope.chat, request_id])
    receipt_path = root / (key + ".outbound.json")
    if not receipt_path.exists():
        raise ConnectorError("outbound_claim_required")
    receipt = read_json(receipt_path)
    if (receipt.get("approval") != expected or receipt.get("provider") != scope.provider
            or receipt.get("request") != key or receipt.get("status") != "unknown"):
        raise ConnectorError("outbound_claim_mismatch")
    try:
        fd = os.open(root / (key + ".dispatch"), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ConnectorError("already_dispatched") from None
    os.close(fd)
