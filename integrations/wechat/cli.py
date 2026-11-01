"""Run with python -m integrations.wechat.cli; imports no WeChat SDK by default."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile

from .model import ConnectorError, Message, Page, PRESETS, Scope
from .runtime import approval, capture, claim_dispatch, desktop_lock, restart_capture, submit

ROOT = Path(__file__).resolve().parents[2]


def worker(request: dict) -> dict:
    from contextlib import redirect_stdout, redirect_stderr
    from .providers import load
    if request.get("live") is not True:
        raise ConnectorError("explicit_live_required")
    scope = Scope(**request["scope"])
    if request.get("action") == "read" and (
        type(request.get("limit")) is not int or not 1 <= request["limit"] <= 500
        or type(request.get("offset")) is not int or not 0 <= request["offset"] <= 100_000
    ):
        raise ConnectorError("invalid_limit")
    if request.get("action") == "send":
        claim_dispatch(Path(request["root"]), scope, request["text"], request["request_id"])
    # Native libraries print account names/key-cache paths; never pass those logs on.
    with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
        provider = load(scope, request.get("command", []))
        if request["action"] == "list-chats":
            if scope.provider != "replica":
                raise ConnectorError("conversation_listing_not_supported")
            return {"conversations": provider.conversations(scope), "truncated_at": 5000}
        if request["action"] == "capture":
            state = capture(Path(request["root"]), scope, lambda limit, offset: provider.read(scope, limit, offset),
                            page_size=request["page_size"], max_messages=request["max_messages"])
            return {k: v for k, v in state.items() if k != "messages"} | {"count": len(state["messages"])}
        if request["action"] == "read":
            return asdict(provider.read(scope, request["limit"], request["offset"]))
        if request["action"] == "send":
            return {"status": provider.send(scope, request["text"])}
    raise ConnectorError("unknown_action")


def isolated(python: str, request: dict, timeout: int) -> dict:
    executable = Path(python)
    if not executable.is_absolute() or not executable.is_file():
        raise ConnectorError("absolute_python_required")
    # A separate Python 3.12 environment can host Windows SDKs without modifying
    # the Python 3.13 production backend or its dependency lock.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([str(executable), "-m", "integrations.wechat.cli", "worker"],
                                   cwd=ROOT, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                   shell=False, start_new_session=os.name != "nt")
        try:
            process.communicate(json.dumps(request).encode("utf-8"), timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None:
                process.kill()
            process.wait()
            raise ConnectorError("worker_interrupted_result_unknown") from None
        if process.returncode or output.tell() > 8_000_000:
            raise ConnectorError("worker_failed")
        output.seek(0)
        try:
            value = json.load(output)
        except (ValueError, UnicodeError):
            raise ConnectorError("upstream_contract_changed") from None
        if not isinstance(value, dict) or "error" in value:
            raise ConnectorError("worker_failed")
        return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["catalog", "list-chats", "capture", "prepare-send", "send", "worker"])
    parser.add_argument("--provider", choices=list(PRESETS), default="usechat")
    parser.add_argument("--account", default="synthetic-account")
    parser.add_argument("--chat", default="synthetic-chat")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--usechat-command", nargs="+", default=[])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-messages", type=int, default=1000)
    parser.add_argument("--restart", action="store_true", help="archive previous candidate and restart scan")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--runtime-root", type=Path, default=ROOT / ".local-runtime" / "wechat")
    parser.add_argument("--text", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--approval-hash", default="")
    args = parser.parse_args(argv)
    try:
        if args.action == "worker":
            request = json.loads(sys.stdin.buffer.read(1_000_000))
            print(json.dumps(worker(request), ensure_ascii=True))
            return 0
        if args.action == "catalog":
            # find_spec only, not import: discovering packages cannot touch WeChat.
            modules = {"pyweixin": "pyweixin", "replica": "wechatauto", "wxautox4": "wxautox4"}
            print(json.dumps({k: {**v, "live_verified": False, "enabled_by_default": False,
                                  "module_in_current_python": bool(importlib.util.find_spec(modules[k]))
                                  if k in modules else None}
                              for k, v in PRESETS.items()}, ensure_ascii=True, indent=2))
            return 0
        scope = Scope(args.provider, args.account, args.chat)
        if args.action == "prepare-send":
            print(json.dumps({"approval_hash": approval(scope, args.text, args.request_id),
                              "scope": asdict(scope), "text": args.text,
                              "status": "preview-only"}, ensure_ascii=True))
            return 0
        if not 1 <= args.timeout <= 300:
            raise ConnectorError("invalid_timeout")
        if not 1 <= args.page_size <= 500 or not 1 <= args.max_messages <= 100_000:
            raise ConnectorError("invalid_limit")
        if args.live and scope.account == "synthetic-account":
            raise ConnectorError("explicit_account_required")
        if args.live and args.provider == "usechat" and not args.allow_model:
            raise ConnectorError("model_authorization_required")
        request = {"scope": asdict(scope), "command": args.usechat_command, "live": True}

        def read(limit, offset):
            if not args.live:
                # Clearly labelled synthetic data, never masquerading as live WeChat.
                all_messages = tuple(Message(f"fixture:{i}", "synthetic-sender", f"Synthetic {i}",
                                             None, "text", "local-db-row") for i in range(7, 0, -1))
                coverage = PRESETS[scope.provider]["history"]
                return Page(all_messages[offset:offset + limit], coverage,
                            offset + limit > len(all_messages) if scope.provider == "replica" else None)
            value = isolated(args.python, {**request, "action": "read", "limit": limit,
                                           "offset": offset}, args.timeout)
            return Page(tuple(Message(**m) for m in value["messages"]),
                        value["coverage"], value["exhausted"])

        root = args.runtime_root / ("live" if args.live else "synthetic")
        with desktop_lock():
            if args.action == "list-chats":
                if scope.provider != "replica":
                    raise ConnectorError("conversation_listing_not_supported")
                value = isolated(args.python, {**request, "action": "list-chats"}, args.timeout) if args.live else {
                    "conversations": [{"id": "synthetic-native-chat", "title": "Synthetic conversation"}]}
                print(json.dumps({"mode": "live-candidate" if args.live else "synthetic", **value}))
            elif args.action == "capture":
                if args.restart:
                    restart_capture(root, scope)
                if args.live:
                    # Keep one SDK/DB instance alive for the whole bounded scan.
                    value = isolated(args.python, {**request, "action": "capture", "root": str(root),
                                                    "page_size": args.page_size,
                                                    "max_messages": args.max_messages}, args.timeout)
                else:
                    value = capture(root, scope, read, page_size=args.page_size,
                                    max_messages=args.max_messages)
                print(json.dumps({"mode": "live-candidate" if args.live else "synthetic",
                                  "count": value.get("count", len(value.get("messages", []))), "status": value["status"],
                                  "coverage": value["coverage"], "complete": False,
                                  "candidate_file": str(root / (scope.key + ".candidate.json"))}))
            else:
                def send(text):
                    if not args.live:
                        return "submitted-unconfirmed"
                    return isolated(args.python, {**request, "action": "send", "text": text,
                                                   "root": str(root), "request_id": args.request_id},
                                    args.timeout)["status"]
                value = submit(root, scope, args.text, args.request_id, args.approval_hash, send)
                print(json.dumps({**value, "mode": "live" if args.live else "synthetic"}))
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ConnectorError) else "connector_failed"
        print(json.dumps({"error": reason, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
