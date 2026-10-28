"""Deterministic fake effect -> lost worker -> verified receipt recovery demo."""
from datetime import datetime, timedelta, timezone
import json

from runtime import FakeAuthority, FakeStore, FakeTool, Request, Runtime, Scope, SimulatedCrash


def main():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scope = Scope("synthetic", "fake-owner", "review")
    request = Request(scope, "work-a", "fixture-a", 1, "synthetic draft review", now + timedelta(hours=1))
    store, authority, tool = FakeStore(), FakeAuthority(), FakeTool()
    authority.scopes.add(scope)
    authority.source(scope, request.source, 1)
    runtime = Runtime(store, authority, tool)
    runtime.enqueue(request, now)
    print(json.dumps({"step": "unapproved", "dispatch": runtime.claim(request.operation, now)}))
    authority.approve(request, now, now + timedelta(minutes=10))
    ticket = runtime.claim(request.operation, now)
    try:
        runtime.dispatch(ticket, now, crash="after_effect")
    except SimulatedCrash:
        print(json.dumps({"step": "worker-crashed", "state": store.get(request.operation).state,
                          "fake_effects": tool.effects}))
    restarted = Runtime(store, authority, tool)
    recovered = restarted.recover(request.operation, now + timedelta(seconds=10))
    print(json.dumps({"step": "recovered", "state": recovered.state, "reason": recovered.reason,
                      "fake_tool_calls": tool.calls, "fake_effects": tool.effects}))
    duplicate = restarted.enqueue(request, now + timedelta(seconds=11))
    print(json.dumps({"step": "duplicate-delivery", "state": duplicate.state,
                      "new_claim": restarted.claim(request.operation, now + timedelta(seconds=11))}))


if __name__ == "__main__":
    main()
