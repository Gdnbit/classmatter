"""Post-R1 document policy using the original BCG, not an Agent write tool."""
from dataclasses import dataclass
from uuid import UUID

from class_os.domain.documents import CreateDocument, ReviseDocument, ChangeDocumentState, decode_document
from class_os.domain.risk import Risk
from .roster import BusinessGateway, QueryGateway, CommandRejected


DOCUMENT_TYPES = (CreateDocument, ReviseDocument, ChangeDocumentState)


@dataclass(frozen=True)
class DocumentDecision:
    level: Risk = Risk.W2
    admitted: bool = True
    requires_approval: bool = True
    policy_version: str = "d2-working-document.v1"


class DocumentBusinessGateway(BusinessGateway):
    # Deliberately closed. The eventual integrated composition must explicitly
    # dispatch domains; registering this adapter cannot enable legacy exits.
    decode_command = staticmethod(decode_document)

    @staticmethod
    def assess_command(tx, binding, command):
        if type(command) not in DOCUMENT_TYPES:
            raise CommandRejected()
        return DocumentDecision()

    @staticmethod
    def command_purpose(command, payload):
        return "manage-class"

    @staticmethod
    def _validate(tx, binding, command, now):
        if type(command) not in DOCUMENT_TYPES:
            raise CommandRejected()
        tx.validate_document(binding, command, now)


class DocumentQueryGateway(QueryGateway):
    @staticmethod
    def audit_purpose(action):
        return "manage-class" if action.startswith("document.") else QueryGateway.audit_purpose(action)

    def documents(self, token, client, csrf, workspace_id, class_id, term_id):
        return self._documents((token, client, csrf, workspace_id), class_id, term_id, None, False)

    def document(self, token, client, csrf, workspace_id, class_id, term_id, document_id, *, history=False):
        if type(document_id) is not UUID or type(history) is not bool:
            raise CommandRejected()
        return self._documents((token, client, csrf, workspace_id), class_id, term_id, document_id, history)

    def _documents(self, credentials, class_id, term_id, document_id, history):
        def read(tx, binding, now):
            if any(type(value) is not UUID for value in (class_id, term_id)):
                raise CommandRejected()
            return tx.read_documents(binding, class_id, term_id, document_id, history)
        action = "document.list" if document_id is None else "document.history" if history else "document.read"
        return self._run(credentials, action, read, class_id=class_id, term_id=term_id, resource_id=document_id)
