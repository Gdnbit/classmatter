"""Fake-only acceptance tests. Process-local fixture state, no network or DB."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest

from runtime import (FakeAuthority, FakeStore, FakeTool, Request, Runtime,
                     Scope, SimulatedCrash, Unavailable)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.scope = Scope("synthetic", "fake-owner", "review")
        self.request = Request(self.scope, "work-a", "fixture-a", 1, "synthetic draft", self.now + timedelta(hours=1))
        self.store, self.authority, self.tool = FakeStore(), FakeAuthority(), FakeTool()
        self.authority.scopes.add(self.scope)
        self.authority.source(self.scope, self.request.source, 1)
        self.runtime = Runtime(self.store, self.authority, self.tool)
        self.key = self.request.operation
        self.runtime.enqueue(self.request, self.now)

    def at(self, seconds):
        return self.now + timedelta(seconds=seconds)

    def approve(self, seconds=600):
        self.authority.approve(self.request, self.now, self.at(seconds))

    def start(self):
        self.approve()
        return self.runtime.claim(self.key, self.now)

    def row(self):
        return self.store.get(self.key)

    def test_no_approval_no_tool_and_explicit_approval_completes_with_receipt(self):
        self.assertIsNone(self.runtime.claim(self.key, self.now))
        self.assertEqual(self.row().state, "approval_wait")
        ticket = self.start()
        receipt = self.runtime.dispatch(ticket, self.now)
        self.assertTrue(self.runtime.finish(ticket, receipt, self.now))
        self.assertEqual(self.row().state, "completed")
        self.assertEqual(self.row().receipt, self.tool.lookup(self.request))
        self.assertEqual((self.tool.calls, self.tool.effects), (1, 1))

    def test_duplicate_enqueue_claim_dispatch_and_finish_do_not_repeat_effect(self):
        ticket = self.start()
        self.assertEqual(self.runtime.enqueue(self.request, self.now), self.row())
        self.assertIsNone(self.runtime.claim(self.key, self.now))
        receipt = self.runtime.dispatch(ticket, self.now)
        self.assertIsNone(self.runtime.dispatch(ticket, self.now))
        self.assertTrue(self.runtime.finish(ticket, receipt, self.now))
        self.assertFalse(self.runtime.finish(ticket, receipt, self.now))
        self.assertIsNone(self.runtime.claim(self.key, self.now))
        self.assertEqual(self.tool.effects, 1)

    def test_idempotency_key_rejects_changed_payload_source_deadline_or_tool(self):
        for fields in ({"value": "different"}, {"source": "different"}, {"revision": 2},
                       {"deadline": self.at(90)}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.runtime.enqueue(replace(self.request, **fields), self.now)
        with self.assertRaises(ValueError):
            replace(self.request, tool="shell")

    def test_each_scope_dimension_changes_operation_and_requires_own_permission(self):
        for field in ("workspace", "owner", "purpose"):
            other = replace(self.request, scope=replace(self.scope, **{field: "other"}))
            self.assertNotEqual(other.operation, self.key)
            self.runtime.enqueue(other, self.now)
            self.assertIsNone(self.runtime.claim(other.operation, self.now))
            self.assertEqual(self.store.get(other.operation).reason, "scope_revoked")
        self.assertEqual(self.tool.calls, 0)

    def test_simultaneous_claims_from_two_workers_issue_one_ticket(self):
        self.approve()
        other = Runtime(self.store, self.authority, self.tool)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda worker: worker.claim(self.key, self.now), (self.runtime, other)))
        self.assertEqual(sum(ticket is not None for ticket in claims), 1)
        self.assertEqual(self.row().attempts, 1)

    def test_forged_ticket_generation_and_self_reported_success_cannot_complete(self):
        ticket = self.start()
        fake = self.tool.expected(self.request)
        self.assertFalse(self.runtime.finish(ticket, fake, self.now))
        self.assertIsNone(self.runtime.dispatch(replace(ticket, generation=99), self.now))
        self.assertIsNone(self.runtime.dispatch(replace(ticket, generation=True), self.now))
        receipt = self.runtime.dispatch(ticket, self.now)
        self.assertFalse(self.runtime.finish(ticket, replace(receipt, result_hash="forged"), self.now))
        self.assertEqual(self.row().state, "running")

    def test_fake_tool_has_idempotent_receipt_but_not_a_real_business_effect(self):
        receipt = self.tool.execute(self.request)
        self.assertEqual(self.tool.execute(self.request), receipt)
        self.assertEqual((self.tool.calls, self.tool.effects), (2, 1))
        with self.assertRaises(ValueError):
            self.tool.execute(replace(self.request, value="different"))

    def test_crash_before_tool_queries_no_effect_then_retries_with_backoff(self):
        ticket = self.start()
        with self.assertRaises(SimulatedCrash):
            self.runtime.dispatch(ticket, self.now, crash="before_effect")
        restarted = Runtime(self.store, self.authority, self.tool)
        self.assertEqual(restarted.recover(self.key, self.at(9)).state, "running")
        recovered = restarted.recover(self.key, self.at(10))
        self.assertEqual((recovered.state, recovered.next_at), ("retry_wait", self.at(12)))
        self.assertIsNone(restarted.claim(self.key, self.at(11)))
        new = restarted.claim(self.key, self.at(12))
        self.assertEqual(new.generation, 2)
        self.assertIsNone(restarted.dispatch(ticket, self.at(12)))
        receipt = restarted.dispatch(new, self.at(12))
        self.assertTrue(restarted.finish(new, receipt, self.at(12)))
        self.assertEqual(self.tool.effects, 1)

    def test_crash_after_effect_recovers_by_receipt_without_second_execute(self):
        ticket = self.start()
        with self.assertRaises(SimulatedCrash):
            self.runtime.dispatch(ticket, self.now, crash="after_effect")
        restarted = Runtime(self.store, self.authority, self.tool)
        result = restarted.recover(self.key, self.at(10))
        self.assertEqual((result.state, result.reason), ("completed", "verified_recovery"))
        self.assertEqual((self.tool.calls, self.tool.effects), (1, 1))
        self.assertIsNone(restarted.claim(self.key, self.at(11)))

    def test_lost_reply_is_unknown_until_lease_expiry_then_receipt_verified(self):
        ticket = self.start()
        self.tool.lose_receipt = True
        self.assertIsNone(self.runtime.dispatch(ticket, self.now))
        self.assertEqual(self.row().state, "unknown")
        self.assertIsNone(self.runtime.claim(self.key, self.at(1)))
        self.assertEqual(self.runtime.recover(self.key, self.at(9)).state, "unknown")
        self.assertEqual(self.runtime.recover(self.key, self.at(10)).state, "completed")
        self.assertEqual(self.tool.calls, 1)

    def test_lookup_outage_never_reexecutes_and_is_bounded_without_hot_loop(self):
        ticket = self.start()
        self.tool.lose_receipt = True
        self.runtime.dispatch(ticket, self.now)
        self.tool.lookup_unavailable = True
        result = self.runtime.recover(self.key, self.at(10))
        self.assertEqual((result.state, result.recovery_checks), ("unknown", 1))
        event_count = len(self.store.events)
        self.runtime.recover(self.key, self.at(11))
        self.assertEqual(len(self.store.events), event_count)
        self.runtime.recover(self.key, self.at(70))
        self.assertEqual(self.runtime.recover(self.key, self.at(130)).reason, "reconciliation_limit")
        self.assertEqual((self.row().state, self.tool.calls, self.tool.effects), ("blocked", 1, 1))

    def test_lookup_outage_can_recover_later_without_replaying_tool(self):
        ticket = self.start()
        self.tool.lose_receipt = True
        self.runtime.dispatch(ticket, self.now)
        self.tool.lookup_unavailable = True
        self.runtime.recover(self.key, self.at(10))
        self.tool.lookup_unavailable = False
        self.assertEqual(self.runtime.recover(self.key, self.at(70)).state, "completed")
        self.assertEqual(self.tool.calls, 1)

    def test_retry_schedule_exponential_and_attempt_limit_terminal(self):
        self.approve()
        self.tool.fail_before = 10
        for start, next_at in ((0, 2), (2, 6), (6, None)):
            ticket = self.runtime.claim(self.key, self.at(start))
            self.runtime.dispatch(ticket, self.at(start))
            if next_at is not None:
                self.assertEqual(self.row().next_at, self.at(next_at))
                self.assertIsNone(self.runtime.claim(self.key, self.at(next_at - 1)))
        self.assertEqual((self.row().state, self.row().attempts, self.tool.effects), ("exhausted", 3, 0))
        self.assertIsNone(self.runtime.claim(self.key, self.at(60)))

    def test_approval_expiry_rechecked_before_dispatch_and_at_exact_boundary(self):
        self.approve(2)
        ticket = self.runtime.claim(self.key, self.now)
        self.assertIsNone(self.runtime.dispatch(ticket, self.at(2)))
        self.assertEqual(self.row().reason, "approval_expired")
        self.assertEqual(self.tool.calls, 0)

    def test_revoked_approval_before_dispatch_blocks_execution(self):
        ticket = self.start()
        self.authority.revoke(self.request)
        self.assertIsNone(self.runtime.dispatch(ticket, self.now))
        self.assertEqual((self.row().reason, self.tool.effects), ("approval_revoked", 0))

    def test_revoked_approval_after_effect_does_not_undo_effect_or_mark_completed(self):
        ticket = self.start()
        receipt = self.runtime.dispatch(ticket, self.now)
        self.authority.revoke(self.request)
        self.assertFalse(self.runtime.finish(ticket, receipt, self.now))
        self.assertEqual((self.row().state, self.tool.effects), ("blocked", 1))
        self.assertEqual(self.runtime.recover(self.key, self.at(10)).state, "blocked")

    def test_new_approval_generation_cannot_authorize_old_ticket(self):
        ticket = self.start()
        self.approve()
        self.assertIsNone(self.runtime.dispatch(ticket, self.now))
        self.assertEqual(self.row().reason, "approval_changed")

    def test_changed_source_and_scope_permission_stop_resumption(self):
        for change in ("source", "scope"):
            with self.subTest(change=change):
                self.setUp()
                ticket = self.start()
                with self.assertRaises(SimulatedCrash):
                    self.runtime.dispatch(ticket, self.now, crash="after_effect")
                if change == "source":
                    self.authority.source(self.scope, self.request.source, 2, active=False)
                else:
                    self.authority.scopes.remove(self.scope)
                result = self.runtime.recover(self.key, self.at(10))
                self.assertEqual(result.state, "blocked")
                self.assertIsNone(result.receipt)
                self.assertEqual(self.tool.effects, 1)

    def test_cancel_before_dispatch_and_after_effect_rejects_late_completion(self):
        for dispatched in (False, True):
            with self.subTest(dispatched=dispatched):
                self.setUp()
                ticket = self.start()
                receipt = self.runtime.dispatch(ticket, self.now) if dispatched else self.tool.expected(self.request)
                self.runtime.cancel(self.key, self.now)
                self.assertFalse(self.runtime.finish(ticket, receipt, self.now))
                self.assertIsNone(self.runtime.dispatch(ticket, self.now))
                self.assertEqual(self.runtime.recover(self.key, self.at(10)).state, "cancelled")
                self.assertEqual(self.tool.effects, int(dispatched))

    def test_terminal_cancel_is_idempotent_and_does_not_change_completed_work(self):
        ticket = self.start()
        receipt = self.runtime.dispatch(ticket, self.now)
        self.runtime.finish(ticket, receipt, self.now)
        self.assertEqual(self.runtime.cancel(self.key, self.now).state, "completed")

    def test_expired_lease_rejects_finish_but_recovery_checks_the_real_receipt(self):
        ticket = self.start()
        receipt = self.runtime.dispatch(ticket, self.now)
        self.assertFalse(self.runtime.finish(ticket, receipt, self.at(10)))
        self.assertEqual(self.runtime.recover(self.key, self.at(10)).state, "completed")

    def test_expired_approval_at_recovery_blocks_even_with_actual_receipt(self):
        self.approve(5)
        ticket = self.runtime.claim(self.key, self.now)
        with self.assertRaises(SimulatedCrash):
            self.runtime.dispatch(ticket, self.now, crash="after_effect")
        self.assertEqual(self.runtime.recover(self.key, self.at(10)).reason, "approval_expired")
        self.assertEqual(self.tool.calls, 1)

    def test_deadline_stops_dispatch_or_recovery(self):
        self.approve()
        self.assertIsNone(self.runtime.claim(self.key, self.at(3600)))
        self.assertEqual(self.row().reason, "deadline")

    def test_corrupted_receipt_is_blocked_not_business_success(self):
        ticket = self.start()
        with self.assertRaises(SimulatedCrash):
            self.runtime.dispatch(ticket, self.now, crash="after_effect")
        original = self.tool._receipts[self.key]
        for changed in (replace(original, request_hash="bad"), replace(original, result_hash="bad"),
                        replace(original, tool="unknown")):
            self.tool._receipts[self.key] = changed
            self.assertIsNone(self.row().receipt)
            self.assertFalse(self.runtime.finish(ticket, changed, self.now))
        self.assertEqual(self.runtime.recover(self.key, self.at(10)).reason, "receipt_mismatch")

    def test_failed_claim_state_event_commit_never_returns_ticket_or_dispatches(self):
        self.approve()
        self.store.fail_next_write = True
        count = len(self.store.events)
        with self.assertRaises(Unavailable):
            self.runtime.claim(self.key, self.now)
        self.assertEqual((self.row().state, len(self.store.events), self.tool.calls), ("approval_wait", count, 0))

    def test_failed_completion_commit_can_recover_without_duplicate_effect(self):
        ticket = self.start()
        receipt = self.runtime.dispatch(ticket, self.now)
        self.store.fail_next_write = True
        with self.assertRaises(Unavailable):
            self.runtime.finish(ticket, receipt, self.now)
        self.assertEqual(self.row().state, "running")
        restarted = Runtime(self.store, self.authority, self.tool)
        self.assertEqual(restarted.recover(self.key, self.at(10)).state, "completed")
        self.assertEqual(self.tool.effects, 1)

    def test_unknown_tool_and_unbounded_configuration_rejected(self):
        for fields in ({"revision": True}, {"revision": 0}, {"value": ""}, {"value": "x" * 2001},
                       {"key": "../unsafe"}, {"tool": "http.request"},
                       {"deadline": self.now.replace(tzinfo=None)}):
            with self.subTest(fields=list(fields)), self.assertRaises(ValueError):
                replace(self.request, **fields)
        for policy in (0, True, 61):
            with self.assertRaises(ValueError):
                Runtime(self.store, self.authority, self.tool, max_attempts=policy)
        with self.assertRaises(ValueError):
            Runtime(self.store, self.authority, object())

    def test_non_utc_operation_times_refused(self):
        bad = self.now.replace(tzinfo=timezone(timedelta(hours=8)))
        with self.assertRaises(ValueError):
            self.runtime.claim(self.key, bad)

    def test_source_revision_rollback_and_approval_payload_substitution_refused(self):
        with self.assertRaises(ValueError):
            self.authority.source(self.scope, self.request.source, 1)
        self.approve()
        changed = replace(self.request, value="changed")
        self.assertEqual(self.authority.check(changed, self.now)[0], "approval_required")

    def test_events_record_metadata_only_and_no_generated_text(self):
        ticket = self.start()
        receipt = self.runtime.dispatch(ticket, self.now)
        self.runtime.finish(ticket, receipt, self.now)
        self.assertEqual([event.state for event in self.store.events],
                         ["approval_wait", "running", "running", "completed"])
        self.assertNotIn(self.request.value, repr(self.store.events))

    def test_demo_executes_actual_recovery_with_one_fake_effect(self):
        completed = subprocess.run([sys.executable, "demo.py"], cwd=Path(__file__).parent,
                                   capture_output=True, text=True, check=True)
        steps = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertIsNone(steps[0]["dispatch"])
        self.assertEqual(steps[1]["state"], "running")
        self.assertEqual((steps[2]["state"], steps[2]["fake_tool_calls"], steps[2]["fake_effects"]),
                         ("completed", 1, 1))
        self.assertIsNone(steps[3]["new_claim"])

    def test_replacement_worker_cannot_weaken_stored_retry_or_lease_policy(self):
        for config in ({"max_attempts": 60}, {"lease_seconds": 60}, {"backoff_seconds": 1}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                Runtime(self.store, self.authority, self.tool, **config)

    def test_recovery_of_claim_without_dispatch_retries_only_after_no_effect_proof(self):
        self.start()
        recovered = self.runtime.recover(self.key, self.at(10))
        self.assertEqual(recovered.state, "retry_wait")
        self.assertEqual(self.tool.calls, 0)

    def test_unexpected_receipt_without_dispatch_intent_cannot_complete(self):
        self.start()
        self.tool.execute(self.request)  # deliberately corrupt the fixture protocol
        result = self.runtime.recover(self.key, self.at(10))
        self.assertEqual((result.state, result.reason), ("blocked", "unexpected_receipt"))

    def test_transient_failure_retries_then_succeeds_with_one_effect(self):
        ticket = self.start()
        self.tool.fail_before = 1
        self.runtime.dispatch(ticket, self.now)
        new = self.runtime.claim(self.key, self.at(2))
        receipt = self.runtime.dispatch(new, self.at(2))
        self.assertTrue(self.runtime.finish(new, receipt, self.at(2)))
        self.assertEqual((self.tool.calls, self.tool.effects), (2, 1))

    def test_approval_revoked_during_retry_wait_prevents_another_attempt(self):
        ticket = self.start()
        self.tool.fail_before = 1
        self.runtime.dispatch(ticket, self.now)
        self.authority.revoke(self.request)
        self.assertIsNone(self.runtime.claim(self.key, self.at(2)))
        self.assertEqual((self.row().reason, self.tool.calls), ("approval_revoked", 1))

    def test_source_changed_after_claim_prevents_first_tool_call(self):
        ticket = self.start()
        self.authority.source(self.scope, self.request.source, 2)
        self.assertIsNone(self.runtime.dispatch(ticket, self.now))
        self.assertEqual((self.row().reason, self.tool.calls), ("source_changed", 0))

    def test_enqueue_commit_failure_has_no_ghost_work_or_event(self):
        other = replace(self.request, key="other-work")
        self.store.fail_next_write = True
        count = len(self.store.events)
        with self.assertRaises(Unavailable):
            self.runtime.enqueue(other, self.now)
        with self.assertRaises(KeyError):
            self.store.get(other.operation)
        self.assertEqual(len(self.store.events), count)

    def test_repeated_unapproved_claims_do_not_append_identical_events(self):
        self.runtime.claim(self.key, self.now)
        count = len(self.store.events)
        self.runtime.claim(self.key, self.at(1))
        self.assertEqual(len(self.store.events), count)


if __name__ == "__main__":
    unittest.main()
