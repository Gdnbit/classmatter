"""Fixed D2 document SQL. No HTTP/runtime activation until lifecycle acceptance."""
from uuid import uuid4

from sqlalchemy import text

from class_os.application.roster import CommandRejected, fingerprint
from class_os.domain.documents import CreateDocument, ReviseDocument, next_document_state, content
from class_os.domain.roster import Receipt
from .roster import PostgresBusinessStore
from .conversation_control import ConversationTransaction


class DocumentStore(PostgresBusinessStore):
    def __init__(self, database, restrictions):
        if database.profile not in ("workbench-d2", "workspace-chat-d3"):
            raise ValueError("Explicit D2 document profile required")
        super().__init__(database)
        self.restrictions = restrictions

    def _transaction(self, connection):
        if connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() != "0027":
            raise RuntimeError("Explicit D2 document schema required")
        return DocumentTransaction(connection, self)


class DocumentTransaction(ConversationTransaction):
    def authorize_boundary(self, binding, action, proposal_id):
        # No imported/retired source may gain new rights through a new pack.
        # Native D1 restriction/transfer checks remain mandatory too.
        super().authorize_boundary(binding, action, proposal_id)
        self._anchor(binding)  # Requires the original initialized protected authority.
        if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.conversation_import)
            OR EXISTS(SELECT 1 FROM class_os.conversation_admission)
            OR EXISTS(SELECT 1 FROM class_os.conversation_control WHERE transfer_id IS NOT NULL)""")).scalar_one():
            raise CommandRejected()
        if action not in ("document.list", "document.read", "document.history", "command.preview",
                          "command.approve", "command.reject", "command.commit", "command.status"):
            raise CommandRejected()
        if proposal_id is not None:
            proposal = self.proposal(binding["workspace_id"], proposal_id)
            if not proposal or proposal["actor_id"] != binding["actor_id"] or proposal["payload"].get("command") not in (
                    "document.create", "document.revise", "document.archive", "document.restore"):
                raise CommandRejected()

    def _document_header(self, binding, document_id):
        return self._connection.execute(text("""SELECT document_id,class_id,term_id,version,status,updated_at
            FROM class_os.working_document WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND document_id=:d"""),
            {**binding, "d": document_id}).mappings().one_or_none()

    def validate_document(self, binding, command, now):
        context = self.class_context(binding["workspace_id"], command.class_id, command.term_id)
        if not context or context["status"] != "active" or context["term_status"] != "active":
            raise CommandRejected()
        current = self._document_header(binding, command.document_id)
        if current is not None and now < current["updated_at"]:
            raise CommandRejected()
        header = {key: value for key, value in current.items() if key != "updated_at"} if current else None
        try:
            return next_document_state(command, header)
        except ValueError:
            raise CommandRejected() from None

    def apply(self, binding, command, now):
        status, version = self.validate_document(binding, command, now)
        values = {**binding, "d": command.document_id, "c": command.class_id, "t": command.term_id,
                  "status": status, "version": version, "now": now, "operation": command.operation}
        if type(command) is CreateDocument:
            self._mutate(text("""INSERT INTO class_os.working_document
                (workspace_id,document_id,owner_id,class_id,term_id,status,version,created_at,updated_at)
                VALUES(:workspace_id,:d,:actor_id,:c,:t,:status,:version,:now,:now)"""), values)
        else:
            self._mutate(text("""UPDATE class_os.working_document SET status=:status,version=:version,updated_at=:now
                WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND document_id=:d
                AND class_id=:c AND term_id=:t AND version=:previous"""), {**values, "previous": command.expected_version})
        if type(command) in (CreateDocument, ReviseDocument):
            values.update(title=command.title, body=command.body, format=command.format)
        else:
            previous = self._connection.execute(text("""SELECT title,body,format FROM class_os.working_document_revision
                WHERE workspace_id=:workspace_id AND document_id=:d AND version=:previous"""),
                {**values, "previous": command.expected_version}).mappings().one()
            values.update(previous)
        self._mutate(text("""INSERT INTO class_os.working_document_revision
            (workspace_id,document_id,version,status,title,body,format,operation,created_by,created_at)
            VALUES(:workspace_id,:d,:version,:status,:title,:body,:format,:operation,:actor_id,:now)"""), values)
        return Receipt(uuid4(), command.document_id, version)

    def read_documents(self, binding, class_id, term_id, document_id, history):
        if not self.class_context(binding["workspace_id"], class_id, term_id):
            raise CommandRejected()
        values = {**binding, "c": class_id, "t": term_id, "d": document_id}
        if document_id is None:
            return tuple(dict(row) for row in self._connection.execute(text("""SELECT d.document_id,d.class_id,d.term_id,
                d.status,d.version,d.created_at,d.updated_at,r.title,r.format FROM class_os.working_document d
                JOIN class_os.working_document_revision r USING(workspace_id,document_id,version,status)
                WHERE d.workspace_id=:workspace_id AND d.owner_id=:actor_id AND d.class_id=:c AND d.term_id=:t
                ORDER BY d.updated_at DESC,d.document_id LIMIT 201"""), values).mappings())
        header = self._document_header(binding, document_id)
        if not header or header["class_id"] != class_id or header["term_id"] != term_id:
            raise CommandRejected()
        # Two fixed statements, no user-supplied identifiers or SQL fragments.
        statement = """SELECT version,status,title,body,format,operation,created_by,created_at
            FROM class_os.working_document_revision WHERE workspace_id=:workspace_id AND document_id=:d
            ORDER BY version DESC LIMIT 201""" if history else """SELECT version,status,title,body,format,operation,created_by,created_at
            FROM class_os.working_document_revision WHERE workspace_id=:workspace_id AND document_id=:d AND version=:version"""
        rows = tuple(dict(row) for row in self._connection.execute(text(statement), {**values, "version": header["version"]}).mappings())
        return rows if history else {**dict(header), **rows[0]}

    def document_page(self, binding, class_id, term_id, document_id, offset, expected_snapshot):
        if not self.class_context(binding['workspace_id'], class_id, term_id):
            raise CommandRejected()
        values = {**binding, 'c': class_id, 't': term_id, 'd': document_id}
        if document_id is None:
            statement = """SELECT d.document_id,d.class_id,d.term_id,d.status,d.version,d.created_at,d.updated_at,
                r.title,r.format FROM class_os.working_document d
                JOIN class_os.working_document_revision r USING(workspace_id,document_id,version,status)
                WHERE d.workspace_id=:workspace_id AND d.owner_id=:actor_id AND d.class_id=:c AND d.term_id=:t
                ORDER BY d.updated_at DESC,d.document_id LIMIT 10001"""
        else:
            header = self._document_header(binding, document_id)
            if not header or header['class_id'] != class_id or header['term_id'] != term_id:
                raise CommandRejected()
            # History pages contain metadata only; fetch each bounded body by
            # immutable version. Never materialize thousands of large bodies.
            statement = """SELECT version,status,title,format,operation,created_by,created_at
                FROM class_os.working_document_revision WHERE workspace_id=:workspace_id AND document_id=:d
                ORDER BY version DESC LIMIT 10001"""
        rows = tuple(dict(row) for row in self._connection.execute(text(statement), values).mappings())
        if len(rows) > 10000:
            raise CommandRejected()
        digest_rows = [{key: str(value) if type(value) is not int else value for key, value in row.items()} for row in rows]
        snapshot = fingerprint({'workspace': str(binding['workspace_id']), 'owner': str(binding['actor_id']),
                                'class': str(class_id), 'term': str(term_id),
                                'document': str(document_id) if document_id else None, 'items': digest_rows})
        if expected_snapshot is not None and snapshot != expected_snapshot:
            raise CommandRejected()
        return {'workspace_id': binding['workspace_id'], 'class_id': class_id, 'term_id': term_id,
                **({'document_id': document_id} if document_id is not None else {}),
                'data': rows[offset:offset + 50], 'snapshot': snapshot,
                'next_offset': offset + 50 if offset + 50 < len(rows) else None}

    def document_revision(self, binding, class_id, term_id, document_id, version):
        current = self._document_header(binding, document_id)
        if (not current or version > current['version'] or current['class_id'] != class_id or current['term_id'] != term_id
                or not self.class_context(binding['workspace_id'], class_id, term_id)):
            raise CommandRejected()
        row = self._connection.execute(text("""SELECT version,status,title,body,format,operation,created_by,created_at
            FROM class_os.working_document_revision WHERE workspace_id=:workspace_id AND document_id=:d AND version=:v"""),
            {**binding, 'd': document_id, 'v': version}).mappings().one_or_none()
        if row is None:
            raise CommandRejected()
        return dict(row)


def validate_document_integrity(connection):
    """Checkpoint validation; never grants activation or business-write rights."""
    if connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.working_document d
        LEFT JOIN class_os.working_document_revision r USING(workspace_id,document_id)
        GROUP BY d.workspace_id,d.document_id,d.version
        HAVING count(r.version)<>d.version OR min(r.version)<>1 OR max(r.version)<>d.version
            OR max(r.created_at)<>d.updated_at)
        OR EXISTS(SELECT 1 FROM class_os.working_document_revision r
        JOIN class_os.working_document d USING(workspace_id,document_id)
        LEFT JOIN class_os.working_document_revision p ON p.workspace_id=r.workspace_id
            AND p.document_id=r.document_id AND p.version=r.version-1
        WHERE r.created_by<>d.owner_id OR r.created_at<d.created_at OR r.created_at>d.updated_at
            OR (r.version=1 AND (r.operation<>'document.create' OR r.status<>'draft' OR r.created_at<>d.created_at))
            OR (r.version>1 AND (p.version IS NULL OR r.created_at<p.created_at OR NOT (
                (r.operation='document.revise' AND p.status='draft' AND r.status='draft')
                OR (r.operation='document.archive' AND p.status='draft' AND r.status='archived'
                    AND (r.title,r.body,r.format)=(p.title,p.body,p.format))
                OR (r.operation='document.restore' AND p.status='archived' AND r.status='draft'
                    AND (r.title,r.body,r.format)=(p.title,p.body,p.format))))))""")).scalar_one():
        raise ValueError("Invalid document revision chain")
    rows = connection.execute(text("SELECT title,body,format FROM class_os.working_document_revision LIMIT 10001")).all()
    if len(rows) > 10000:
        raise ValueError("Document checkpoint bound exceeded")
    for row in rows:
        content(*row)
