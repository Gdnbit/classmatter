"""Synthetic connector contract/failure tests. Never imports an installed WeChat SDK."""
from dataclasses import asdict
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from integrations.wechat.cli import isolated, main, worker
from integrations.wechat.model import ConnectorError, Message, Page, Scope
from integrations.wechat.providers import PyWeixin, Replica, UseChat, WxAutoX
from integrations.wechat.runtime import approval, capture, claim_dispatch, read_json, restart_capture, submit


def message(index, text=None):
    return Message(f"shard:{index}", "synthetic-sender", text or f"Synthetic {index}",
                   None, "text", "local-db-row")


def reader(rows):
    def read(limit, offset):
        return Page(tuple(rows[offset:offset + limit]), "paginated-local",
                    offset + limit > len(rows))
    return read


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = Scope("replica", "synthetic-a", "synthetic-chat")
        self.rows = [message(i) for i in range(7, 0, -1)]

    def test_backfill_then_resume_reads_every_message(self):
        first = capture(self.root, self.scope, reader(self.rows), page_size=2, max_messages=3)
        self.assertEqual(first["status"], "limit-reached")
        second = capture(self.root, self.scope, reader(self.rows), page_size=2, max_messages=20)
        self.assertEqual(second["status"], "source-exhausted")
        self.assertEqual(second["messages"], [asdict(m) for m in self.rows])
        self.assertFalse(second["complete"])
        self.assertFalse(second["business_fact"])
        self.assertEqual(second["attachments"], "metadata-only")

    def test_exact_page_multiple_requires_empty_tail(self):
        calls = []
        read = reader(self.rows[:4])
        def counted(limit, offset):
            calls.append(offset)
            return read(limit, offset)
        result = capture(self.root, self.scope, counted, page_size=2, max_messages=20)
        self.assertEqual(result["status"], "source-exhausted")
        self.assertIn(4, calls)

    def test_insert_delete_edit_and_reorder_all_refuse_resume(self):
        for changed in ([message(9), *self.rows], self.rows[:1] + self.rows[2:],
                        [self.rows[0], message(6, "changed"), *self.rows[2:]],
                        [self.rows[1], self.rows[0], *self.rows[2:]]):
            with self.subTest(changed=changed):
                for file in self.root.iterdir():
                    file.unlink()
                capture(self.root, self.scope, reader(self.rows), page_size=2, max_messages=3)
                with self.assertRaisesRegex(ConnectorError, "source_changed"):
                    capture(self.root, self.scope, reader(changed), page_size=2, max_messages=20)
                state = read_json(next(self.root.glob("*.candidate.json")))
                self.assertEqual(len(state["messages"]), 3)
                self.assertFalse(state["complete"])

    def test_account_chat_and_provider_scopes_are_distinct(self):
        capture(self.root, self.scope, reader(self.rows), max_messages=2)
        other = Scope("replica", "synthetic-b", "synthetic-chat")
        capture(self.root, other, reader(self.rows), max_messages=2)
        self.assertEqual(len(list(self.root.glob("*.candidate.json"))), 2)

    def test_corrupt_checkpoint_fails_without_overwrite(self):
        path = self.root / (self.scope.key + ".candidate.json")
        path.write_text('{"scope": {}}', encoding="utf-8")
        with self.assertRaisesRegex(ConnectorError, "invalid_local_state"):
            capture(self.root, self.scope, reader(self.rows))
        self.assertEqual(path.read_text(), '{"scope": {}}')

    def test_cancellation_retains_checkpoint(self):
        result = capture(self.root, self.scope, reader(self.rows), cancelled=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["messages"], [])

    def test_fault_after_page_keeps_last_durable_page(self):
        calls = 0
        def read(limit, offset):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ConnectorError("upstream_failed")
            return reader(self.rows)(limit, offset)
        with self.assertRaises(ConnectorError):
            capture(self.root, self.scope, read, page_size=2)
        state = read_json(next(self.root.glob("*.candidate.json")))
        self.assertEqual(len(state["messages"]), 2)
        self.assertFalse(state["source_exhausted"])

    def test_duplicate_native_id_refused(self):
        with self.assertRaisesRegex(ConnectorError, "duplicate_native_identity"):
            capture(self.root, self.scope, reader([message(1), message(1)]))

    def test_bad_limits_are_rejected_before_read(self):
        read = Mock()
        for kwargs in ({"page_size": 0}, {"max_messages": 0}, {"page_size": True}):
            with self.assertRaises(ConnectorError):
                capture(self.root, self.scope, read, **kwargs)
        read.assert_not_called()

    def test_ui_read_never_claims_exhaustion(self):
        scope = Scope("pyweixin", "synthetic-a", "synthetic-chat")
        result = capture(self.root, scope, lambda *_: Page(tuple(self.rows), "requested-window", None))
        self.assertEqual(result["status"], "observed")
        self.assertIsNone(result["source_exhausted"])
        self.assertFalse(result["complete"])

    def test_stalled_source_does_not_loop(self):
        with self.assertRaisesRegex(ConnectorError, "source_not_progressing"):
            capture(self.root, self.scope, lambda *_: Page((), "paginated-local", False))

    def test_explicit_restart_archives_original_candidate(self):
        capture(self.root, self.scope, reader(self.rows), max_messages=2)
        original = next(self.root.glob("*.candidate.json")).read_bytes()
        restart_capture(self.root, self.scope)
        self.assertEqual(next(self.root.glob("*.previous-*.json")).read_bytes(), original)
        result = capture(self.root, self.scope, reader([message(9), *self.rows]))
        self.assertEqual(len(result["messages"]), 8)


class ProviderTests(unittest.TestCase):
    def test_replica_passes_native_pagination_and_shard_id(self):
        db = Mock()
        db.account = "synthetic-a"
        db.get_messages.return_value = [
            {"shard": "m0", "local_id": 1, "content": "synthetic one", "sender_id": 2},
            {"shard": "m1", "local_id": 1, "content": "synthetic two", "sender_id": 2}]
        scope = Scope("replica", "synthetic-a", "synthetic-chat")
        page = Replica(db).read(scope, 20, 10)
        db.get_messages.assert_called_once_with(scope.chat, limit=20, offset=10)
        self.assertNotEqual(page.messages[0].source_id, page.messages[1].source_id)
        self.assertIsNone(page.messages[0].sender)
        with self.assertRaisesRegex(ConnectorError, "send_not_supported"):
            Replica(db).send(scope, "synthetic")

    def test_replica_missing_shard_fails(self):
        db = Mock()
        db.account = "a"
        db.get_messages.return_value = [{"local_id": 1, "content": "synthetic"}]
        with self.assertRaises(ConnectorError):
            Replica(db).read(Scope("replica", "a", "b"), 20, 0)

    def test_replica_account_fallback_is_rejected_before_returning_rows(self):
        db = Mock(account="a")
        def switched(*args, **kwargs):
            db.account = "other-account"
            return []
        db.get_messages.side_effect = switched
        with self.assertRaisesRegex(ConnectorError, "account_changed"):
            Replica(db).read(Scope("replica", "a", "b"), 20, 0)

    def test_replica_empty_initial_source_is_not_complete(self):
        db = Mock(account="a")
        db.get_messages.return_value = []
        with self.assertRaisesRegex(ConnectorError, "empty_or_unavailable_source"):
            Replica(db).read(Scope("replica", "a", "b"), 20, 0)

    def test_replica_account_cannot_escape_selected_directory(self):
        for account in ("..", "../other", "other/account", "other\\account"):
            with self.assertRaises(ConnectorError):
                Scope("replica", account, "synthetic-chat")

    def test_replica_conversation_selection_uses_exact_native_identity(self):
        db = Mock(account="a")
        db.get_sessions.return_value = [{"username": "synthetic-id"}]
        db.search_contact.return_value = [{"username": "wrong", "remark": "Wrong"},
                                          {"username": "synthetic-id", "remark": "Synthetic group"}]
        self.assertEqual(Replica(db).conversations(Scope("replica", "a", "b")),
                         [{"id": "synthetic-id", "title": "Synthetic group"}])

    def test_usechat_actual_wire_fields_and_target(self):
        invoke = Mock(return_value={"ok": True, "chat": "synthetic-chat", "messages": [
            {"stableMessageKey": "synthetic-id", "senderRole": "self",
             "normalizedText": "synthetic", "observedAt": "not-message-time", "kind": "text"}]})
        scope = Scope("usechat", "synthetic-a", "synthetic-chat")
        page = UseChat([], invoke).read(scope, 20, 0)
        self.assertEqual(page.messages[0].text, "synthetic")
        self.assertIsNone(page.messages[0].timestamp)
        self.assertEqual(page.messages[0].evidence, "visual-inference")
        self.assertIn("--chat", invoke.call_args.args[0])
        invoke.return_value["chat"] = "wrong"
        with self.assertRaises(ConnectorError):
            UseChat([], invoke).read(scope, 20, 0)

    def test_visual_quality_failure_refused(self):
        invoke = Mock(return_value={"chat": "b", "quality": {"ok": False}, "messages": []})
        with self.assertRaises(ConnectorError):
            UseChat([], invoke).read(Scope("usechat", "a", "b"), 20, 0)

    def test_usechat_never_promotes_send_to_verified(self):
        invoke = Mock(return_value={"chat": "b", "text": "synthetic", "sent": True,
                                    "status": "sent-unconfirmed"})
        self.assertEqual(UseChat([], invoke).send(Scope("usechat", "a", "b"), "synthetic"),
                         "submitted-unconfirmed")

    def test_uia_contract_and_duplicate_identical_bubbles(self):
        sdk = Mock()
        sdk.pull_messages.return_value = [{"消息发送人": "synthetic", "消息内容": "repeat"}] * 2
        provider = PyWeixin(sdk)
        scope = Scope("pyweixin", "a", "b")
        page = provider.read(scope, 50, 0)
        sdk.pull_messages.assert_called_once_with(friend="b", number=50, is_json=False,
                                                  close_weixin=False)
        self.assertNotEqual(page.messages[0].source_id, page.messages[1].source_id)
        self.assertEqual(page.messages[0].sender, "synthetic")
        self.assertEqual(provider.send(scope, "synthetic"), "submitted-unconfirmed")
        sdk.send_messages_to_friend.assert_called_once_with(friend="b", messages=["synthetic"],
                                                            close_weixin=False)

    def test_commercial_adapter_checks_target_before_send(self):
        sdk = Mock()
        sdk.ChatInfo.return_value = {"chat_name": "wrong"}
        with self.assertRaises(ConnectorError):
            WxAutoX(sdk).send(Scope("wxautox4", "a", "b"), "synthetic")
        sdk.SendMsg.assert_not_called()

    def test_ui_providers_reject_fake_pagination(self):
        for provider, name in [(UseChat([], Mock()), "usechat"),
                               (PyWeixin(Mock()), "pyweixin"), (WxAutoX(Mock()), "wxautox4")]:
            with self.subTest(name=name), self.assertRaisesRegex(ConnectorError, "history_not_supported"):
                provider.read(Scope(name, "a", "b"), 20, 20)


class OutboundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = Scope("pyweixin", "synthetic-a", "synthetic-chat")

    def test_preview_hash_binds_provider_recipient_content_and_request(self):
        value = approval(self.scope, "synthetic", "request-1")
        for scope, text, request in [(self.scope, "changed", "request-1"),
                                     (Scope("usechat", "synthetic-a", "synthetic-chat"), "synthetic", "request-1"),
                                     (Scope("pyweixin", "synthetic-a", "other"), "synthetic", "request-1"),
                                     (self.scope, "synthetic", "request-2")]:
            send = Mock()
            with self.subTest(scope=scope), self.assertRaisesRegex(ConnectorError, "approval_mismatch"):
                submit(self.root, scope, text, request, value, send)
            send.assert_not_called()

    def test_timeout_blocks_repeat_and_cross_provider_fallback(self):
        send = Mock(side_effect=TimeoutError("private-upstream-message"))
        result = submit(self.root, self.scope, "synthetic", "request-1",
                        approval(self.scope, "synthetic", "request-1"), send)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["retry_allowed"])
        for scope in (self.scope, Scope("usechat", self.scope.account, self.scope.chat)):
            with self.assertRaisesRegex(ConnectorError, "already_attempted"):
                submit(self.root, scope, "synthetic", "request-1",
                       approval(scope, "synthetic", "request-1"), send)
        self.assertEqual(send.call_count, 1)
        self.assertNotIn("private-upstream-message", next(self.root.iterdir()).read_text())

    def test_pending_receipt_exists_before_external_send(self):
        def send(_):
            state = read_json(next(self.root.iterdir()))
            self.assertEqual(state["status"], "unknown")
            return "submitted-unconfirmed"
        result = submit(self.root, self.scope, "synthetic", "request-1",
                        approval(self.scope, "synthetic", "request-1"), send)
        self.assertEqual(result["status"], "submitted-unconfirmed")

    def test_worker_requires_claim_and_blocks_repeated_dispatch(self):
        with self.assertRaisesRegex(ConnectorError, "outbound_claim_required"):
            claim_dispatch(self.root, self.scope, "synthetic", "request-1")
        def send(_):
            claim_dispatch(self.root, self.scope, "synthetic", "request-1")
            with self.assertRaisesRegex(ConnectorError, "already_dispatched"):
                claim_dispatch(self.root, self.scope, "synthetic", "request-1")
            return "submitted-unconfirmed"
        self.assertEqual(submit(self.root, self.scope, "synthetic", "request-1",
                                approval(self.scope, "synthetic", "request-1"), send)["status"],
                         "submitted-unconfirmed")


class CliTests(unittest.TestCase):
    def test_catalog_and_default_capture_are_offline(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["catalog"]), 0)
            catalog = json.loads(output.getvalue())
            self.assertEqual(len(catalog), 4)
            self.assertTrue(all(not p["live_verified"] for p in catalog.values()))
            output.truncate(0)
            output.seek(0)
            self.assertEqual(main(["capture", "--provider", "replica", "--page-size", "2",
                                   "--runtime-root", directory]), 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "synthetic")

    def test_live_requires_account_and_model_opt_in(self):
        for args in (["capture", "--live"], ["capture", "--live", "--account", "operator-selected"]):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(args), 2)
                self.assertIn("required", json.loads(output.getvalue())["error"])

    def test_worker_refuses_accidental_invocation(self):
        with self.assertRaisesRegex(ConnectorError, "explicit_live_required"):
            worker({"scope": asdict(Scope("replica", "a", "b"))})

    def test_actual_isolated_process_has_sanitized_failure(self):
        # Real subprocess; invalid request is rejected before any native SDK import.
        with self.assertRaisesRegex(ConnectorError, "worker_failed"):
            isolated(sys.executable, {"scope": {"private": "must-not-leak"}}, 10)

    def test_scopes_and_message_types_reject_contract_drift(self):
        for value in ("bad\nname", "", "x" * 257):
            with self.assertRaises(ConnectorError):
                Scope("replica", "a", value)
        with self.assertRaises(ConnectorError):
            Message("id", None, {"bad": "shape"}, None, "text", "local-db-row")


if __name__ == "__main__":
    unittest.main()
