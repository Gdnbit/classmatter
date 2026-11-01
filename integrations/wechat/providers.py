"""Explicit SDK calls, loaded only inside a user-invoked isolated worker.

No dependency auto-install, implicit fallback, arbitrary SQL, GUI hot activation,
attachment download, or business database access is implemented here.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess

from .model import ConnectorError, Message, Page, Scope, digest


def _messages(rows, evidence: str, mapper) -> tuple[Message, ...]:
    if not isinstance(rows, list):
        raise ConnectorError("upstream_contract_changed")
    result = []
    occurrences: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ConnectorError("upstream_contract_changed")
        source_id, sender, text, timestamp, kind = mapper(row)
        if source_id is None:
            # A fallback fingerprint is not a native identity. Preserve repeated identical
            # bubbles within one capture; do not deduplicate them by content alone.
            fingerprint = digest([sender, text, timestamp, kind])
            occurrences[fingerprint] = occurrences.get(fingerprint, 0) + 1
            source_id = f"observed:{fingerprint}:{occurrences[fingerprint]}"
        result.append(Message(str(source_id), sender, text, timestamp, str(kind), evidence))
    return tuple(result)


class UseChat:
    def __init__(self, command: list[str], invoke=None):
        self.command = command
        self.invoke = invoke or self._invoke

    def _invoke(self, args: list[str]):
        # Executable path comes from operator CLI configuration, never message text.
        if not self.command or not Path(self.command[0]).is_absolute():
            raise ConnectorError("absolute_executable_required")
        reply = subprocess.run([*self.command, *args], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=60, shell=False, check=False)
        if reply.returncode or len(reply.stdout) > 8_000_000:
            raise ConnectorError("upstream_failed")
        try:
            value = json.loads(reply.stdout)
        except (ValueError, UnicodeError):
            raise ConnectorError("upstream_contract_changed") from None
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise ConnectorError("upstream_failed")
        return value

    def read(self, scope: Scope, limit: int, offset: int) -> Page:
        if offset:
            raise ConnectorError("history_not_supported")
        value = self.invoke(["read", "--app", "wechat", "--chat", scope.chat,
                             "--limit", str(limit), "--format", "json"])
        if value.get("chat") != scope.chat or value.get("quality", {}).get("ok") is False:
            raise ConnectorError("target_or_quality_unverified")
        messages = _messages(value.get("messages"), "visual-inference", lambda r: (
            r.get("stableMessageKey"), r.get("senderName"),
            r.get("normalizedText") or r.get("textExcerpt") or r.get("anchorText") or "",
            None, r.get("kind", "unknown")))
        return Page(messages, "visible-only", None)

    def send(self, scope: Scope, text: str) -> str:
        result = self.invoke(["write", "--app", "wechat", "--chat", scope.chat,
                              "--text", text, "--yes", "--json"])
        # Upstream explicitly returns sent-unconfirmed. Do not promote to verified.
        if result.get("chat") != scope.chat or result.get("text") != text:
            return "unknown"
        return "submitted-unconfirmed" if result.get("sent") is True else "unknown"


class PyWeixin:
    def __init__(self, messages):
        self.messages = messages

    def read(self, scope: Scope, limit: int, offset: int) -> Page:
        if offset:
            raise ConnectorError("history_not_supported")
        rows = self.messages.pull_messages(friend=scope.chat, number=limit,
                                            is_json=False, close_weixin=False)
        messages = _messages(rows, "uia-observation", lambda r: (
            None, r.get("消息发送人"), r["消息内容"],
            None, r.get("消息类型", "unknown")))
        # A short UI result can mean inaccessible elements, not end of history.
        return Page(messages, "requested-window", None)

    def send(self, scope: Scope, text: str) -> str:
        self.messages.send_messages_to_friend(friend=scope.chat, messages=[text],
                                              close_weixin=False)
        return "submitted-unconfirmed"


class Replica:
    def __init__(self, db):
        self.db = db

    def read(self, scope: Scope, limit: int, offset: int) -> Page:
        if self.db.account != scope.account:
            raise ConnectorError("account_changed")
        rows = self.db.get_messages(scope.chat, limit=limit, offset=offset)
        if self.db.account != scope.account:
            raise ConnectorError("account_changed")

        def map_row(row):
            # local_id alone collides across message shards. Never infer sender from ==2.
            if not row.get("shard") or row.get("local_id") is None:
                raise ConnectorError("upstream_contract_changed")
            timestamp = row.get("create_time")
            return (f"{row['shard']}:{row['local_id']}", row.get("sender_username") or None,
                    row.get("content", ""), str(timestamp) if timestamp is not None else None,
                    row.get("type", "unknown"))

        if not rows and not offset:
            # Empty first read cannot distinguish unknown target, unavailable shards,
            # and a legitimately empty chat. Never call it a complete empty archive.
            raise ConnectorError("empty_or_unavailable_source")
        return Page(_messages(rows, "local-db-row", map_row), "paginated-local",
                    len(rows) < limit)

    def send(self, scope: Scope, text: str) -> str:
        raise ConnectorError("send_not_supported")

    def conversations(self, scope: Scope) -> list[dict]:
        if self.db.account != scope.account:
            raise ConnectorError("account_changed")
        rows = self.db.get_sessions(limit=5000)
        result = []
        for row in rows:
            username = row.get("username")
            if not isinstance(username, str) or not username:
                raise ConnectorError("upstream_contract_changed")
            # Exact IDs remain available without asking a teacher to remember them.
            contacts = self.db.search_contact(username)
            exact = [c for c in contacts if c.get("username") == username]
            title = (exact[0].get("remark") or exact[0].get("nick_name")) if exact else None
            result.append({"id": username, "title": title or username})
        if self.db.account != scope.account:
            raise ConnectorError("account_changed")
        return result


class WxAutoX:
    def __init__(self, client):
        self.client = client

    def _open(self, scope: Scope):
        self.client.ChatWith(scope.chat)
        info = self.client.ChatInfo()
        if not isinstance(info, dict) or info.get("chat_name") != scope.chat:
            raise ConnectorError("target_or_quality_unverified")

    def read(self, scope: Scope, limit: int, offset: int) -> Page:
        if offset:
            raise ConnectorError("history_not_supported")
        self._open(scope)
        rows = [{"id": getattr(m, "id", None), "sender": getattr(m, "sender", None),
                 "content": getattr(m, "content", ""), "type": getattr(m, "type", "unknown")}
                for m in self.client.GetAllMessage()][-limit:]
        return Page(_messages(rows, "uia-observation", lambda r: (
            r["id"], r["sender"], r["content"], None, r["type"])), "visible-only", None)

    def send(self, scope: Scope, text: str) -> str:
        self._open(scope)
        self.client.SendMsg(text)
        return "submitted-unconfirmed"


def load(scope: Scope, command: list[str]):
    if os.name != "nt" and scope.provider != "usechat":
        raise ConnectorError("windows_required")
    if scope.provider == "usechat":
        return UseChat(command)
    if scope.provider == "pyweixin":
        return PyWeixin(importlib.import_module("pyweixin").Messages)
    if scope.provider == "wxautox4":
        return WxAutoX(importlib.import_module("wxautox4").WeChat())
    # Import the DB submodule only; never instantiate WeChatGUI or its activation path.
    db_type = importlib.import_module("wechatauto.db").WeChatDB
    return Replica(db_type(account=scope.account))
