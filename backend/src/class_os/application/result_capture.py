"""One SDK turn's fixed provenance, not Memory, a model tool or a writer.

Only the original SDK adapter calls these hooks after actual authorized QG
returns. The short-lived collector has no repository/BCG or credential text.
"""
from dataclasses import dataclass, field
from uuid import UUID

from class_os.domain.conversation_worker import ClaimedRun
from class_os.domain.conversation_results import ProducedResult, QuerySource
from class_os.domain.query_snapshot import WorkSnapshot
from class_os.domain.activity import CreateTask
from class_os.domain.exit_package import checksum
from .identity import digest
from .roster import CommandRejected


_ISSUER = object()


def binding(credentials):
    if (type(credentials) is not tuple or len(credentials) != 4 or type(credentials[3]) is not UUID
            or any(type(value) is not str or not value for value in credentials[:3])):
        raise CommandRejected()
    return (*[digest(value) for value in credentials[:3]], credentials[3])


@dataclass(frozen=True)
class CapturedResult:
    collector: object = field(repr=False)
    result: ProducedResult = field(repr=False)
    issuer: object = field(default=None, repr=False)

    def __post_init__(self):
        if self.issuer is not _ISSUER or type(self.collector) is not ResultCapture or type(self.result) is not ProducedResult:
            raise CommandRejected()

    def verify(self, store, identity, credentials, ticket):
        capture = self.collector
        if (capture.closed or capture.store is not store or capture.identity is not identity or capture.ticket != ticket
                or capture.credentials_binding != binding(credentials) or capture.sealed is not self):
            raise CommandRejected()
        return self.result


class ResultCapture:
    def __init__(self, ticket, credentials, query):
        from .conversation_interaction import ConversationInteractionQuery
        coordinates = binding(credentials)
        if type(ticket) is not ClaimedRun or type(query) is not ConversationInteractionQuery or coordinates[3] != ticket.scope.workspace_id:
            raise CommandRejected()
        self.ticket = ticket
        self.store, self.identity = query.store, query.identity
        self.credentials_binding = coordinates
        self.sdk_run = None
        self.sources = ()
        self.draft = None
        self.output_hash = None
        self.closed = False
        self.sealed = None

    def check(self, run, credentials):
        if self.closed or self.sealed is not None or self.credentials_binding != binding(credentials) or self.sdk_run != run:
            raise CommandRejected()

    def begin(self, run, credentials):
        if type(run) is not UUID or self.sdk_run is not None:
            raise CommandRejected()
        self.sdk_run = run
        self.check(run, credentials)

    def observe_read(self, run, credentials, projection):
        self.check(run, credentials)
        scope = self.ticket.scope
        if (self.output_hash is not None or self.ticket.intent.mode != "read" or type(projection) is not WorkSnapshot
                or projection.class_id != scope.class_id or projection.term_id != scope.term_id or projection.student_id != scope.student_id
                or not self.ticket.run.started_at <= projection.as_of < self.ticket.run.lease_until):
            raise CommandRejected()
        source = QuerySource.from_tool(scope, projection.tool_payload()["source_refs"][0])
        if any(item.receipt_id == source.receipt_id for item in self.sources) or len(self.sources) >= 2:
            raise CommandRejected()
        self.sources = (*self.sources, source)

    def observe_draft(self, run, credentials, task):
        self.check(run, credentials)
        if self.output_hash is not None or self.draft is not None or type(task) is not CreateTask:
            raise CommandRejected()
        ProducedResult("candidate syntax", draft=task).validate_intent(self.ticket.intent)
        self.draft = task

    def completed(self, run, credentials, output):
        self.check(run, credentials)
        if self.output_hash is not None:
            raise CommandRejected()
        result = ProducedResult(output, self.sources, self.draft)
        result.validate_intent(self.ticket.intent)
        self.output_hash = checksum(output)

    def seal(self, run, credentials, result):
        self.check(run, credentials)
        if (type(result) is not ProducedResult or self.output_hash != checksum(result.text)
                or result.sources != self.sources or result.draft != self.draft):
            raise CommandRejected()
        result.validate_intent(self.ticket.intent)
        self.sealed = CapturedResult(self, result, _ISSUER)
        return self.sealed

    def close(self):
        self.closed = True
        self.sources = ()
        self.draft = None
        self.output_hash = None
