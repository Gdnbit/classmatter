"""Human interaction persistence through existing BCG/QG identity and audit UoW.

Only the trusted HTTP/worker composition receives the business gateway. Agent
tools never receive it, a store, a connection, or approval/commit capability.
"""
from .roster import BusinessGateway, QueryGateway, CommandRejected


class WorkspaceChatBusinessGateway(BusinessGateway):
    def send(self, credentials, thread_id, request_id, text):
        return self._run(credentials, "workspace.chat.send",
            lambda tx, binding, now: tx.chat_send(binding, thread_id, request_id, text, now), resource_id=thread_id)

    def claim(self, credentials, thread_id, request_id):
        return self._run(credentials, "workspace.chat.claim",
            lambda tx, binding, now: tx.chat_claim(binding, thread_id, request_id, now), resource_id=thread_id)

    def finish(self, credentials, ticket, state, answer=None, candidate=None, *, duration_ms=None, input_tokens=None, output_tokens=None, answer_required=False, summary_document_id=None):
        def finish(tx, binding, now):
            extras = {'answer_required': answer_required, 'summary_document_id': summary_document_id} if self.store.database.profile == 'classroom-work-d4' else {}
            return tx.chat_finish(binding, ticket, state, answer, candidate, now, duration_ms, input_tokens, output_tokens, **extras)
        return self._run(credentials, "workspace.chat.finish",
            finish, resource_id=ticket["thread_id"])

    def summary_claim(self, credentials, document_id):
        if self.store.database.profile != 'classroom-work-d4':
            raise CommandRejected()
        return self._run(credentials, 'workspace.chat.send',
            lambda tx, binding, now: tx.summary_claim(binding, document_id, now), resource_id=document_id)

    def cancel(self, credentials, thread_id, request_id, expected_version):
        return self._run(credentials, "workspace.chat.cancel",
            lambda tx, binding, now: tx.chat_cancel(binding, thread_id, request_id, expected_version, now), resource_id=thread_id)

    def control(self, credentials, thread_id, expected_version, action):
        if action not in ("archive", "clear"):
            raise CommandRejected()
        return self._run(credentials, "workspace.chat." + action,
            lambda tx, binding, now: tx.chat_control(binding, thread_id, expected_version, action, now), resource_id=thread_id)


class WorkspaceChatQueryGateway(QueryGateway):
    def summary_programs(self, credentials):
        if self.store.database.profile != 'classroom-work-d4':
            raise CommandRejected()
        return self._run(credentials, 'workspace.chat.read', lambda tx, binding, now: tx.summary_programs(binding))

    def summary_context(self, credentials, thread_id, request_id):
        if self.store.database.profile != 'classroom-work-d4':
            return None
        return self._run(credentials, 'workspace.chat.read',
            lambda tx, binding, now: tx.summary_context(binding, thread_id, request_id), resource_id=thread_id)

    def turn(self, credentials, thread_id, request_id):
        return self._run(credentials, "workspace.chat.read",
            lambda tx, binding, now: tx.chat_turn_view(binding, thread_id, request_id), resource_id=thread_id)

    def listing(self, credentials, *, offset=0):
        return self._run(credentials, "workspace.chat.list", lambda tx, binding, now: tx.chat_list(binding, offset=offset))

    def history(self, credentials, thread_id, *, before=None):
        return self._run(credentials, "workspace.chat.read",
            lambda tx, binding, now: tx.chat_history(binding, thread_id, before=before), resource_id=thread_id)

    def recall(self, credentials, thread_id, keyword, *, before):
        return self._run(credentials, "workspace.chat.read",
            lambda tx, binding, now: tx.chat_recall(binding, thread_id, keyword, before=before), resource_id=thread_id)
