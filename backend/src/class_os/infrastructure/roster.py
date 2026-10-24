"""SQL implementation owned exclusively by the synthetic business boundaries."""
from contextlib import contextmanager
from uuid import uuid4

from psycopg.types.json import Jsonb
from sqlalchemy import text

from class_os.domain.roster import ClassView, TermMetadata, CreateClass, CreateStudent, Receipt, StudentView
from .activity import ActivityTransaction
from .exit_package import ExitTransaction
from .model_configuration import ModelConfigurationTransaction
from class_os.domain.model_control import ModelControl
from class_os.domain.exit_package import CreateExitExport


class PostgresBusinessStore:
    def __init__(self, database, *, model_secrets=None):
        self.database = database
        self.model_secrets = model_secrets

    @contextmanager
    def atomic(self):
        with self.database.transaction() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
            connection.execute(text("SELECT pg_advisory_xact_lock(607103017)"))
            yield self._transaction(connection)

    def _transaction(self, connection):
        return BusinessTransaction(connection, self)

    def audit(self, connection, binding, action, outcome, now, metadata):
        event_id = uuid4()
        stored_id = connection.execute(text("""INSERT INTO class_os.business_audit
            (event_id,workspace_id,actor_id,session_digest,purpose,action,outcome,occurred_at,
             proposal_id,payload_hash,receipt_id,resource_id,resource_version,class_id,term_id)
            VALUES(:event_id,:workspace_id,:actor_id,:session_digest,:purpose,:action,:outcome,:now,
                   :proposal_id,:payload_hash,:receipt_id,:resource_id,:resource_version,:class_id,:term_id)
            RETURNING event_id"""),
                           {**binding, **metadata, "event_id": event_id, "action": action, "outcome": outcome, "now": now}).scalar_one()
        return stored_id


class BusinessTransaction(ActivityTransaction, ExitTransaction, ModelConfigurationTransaction):
    def __init__(self, connection, store):
        self._connection, self._store = connection, store

    def _mutate(self, statement, values, *, expected=1):
        """Fixed owning SQL only; fail the enclosing transaction on lost writes."""
        result = self._connection.execute(statement, values)
        if result.rowcount != expected:
            raise RuntimeError("Missing durable business mutation")
        return result

    def audit_log(self, binding, class_id, term_id):
        return tuple(dict(row) for row in self._connection.execute(text("""SELECT event_id,action,outcome,occurred_at,
            proposal_id,payload_hash,receipt_id,resource_id,resource_version FROM class_os.business_audit
            WHERE workspace_id=:w AND actor_id=:a AND class_id=:c AND term_id=:t
            ORDER BY occurred_at DESC,event_id DESC LIMIT 101"""),
            {"w": binding["workspace_id"], "a": binding["actor_id"], "c": class_id, "t": term_id}).mappings())

    def synthetic_workspace(self, workspace_id):
        return self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.workspace w
            CROSS JOIN class_os.database_state s WHERE w.workspace_id=:workspace_id
            AND w.data_mode='synthetic-only' AND s.singleton=true AND s.data_mode='synthetic-only')"""),
            {"workspace_id": workspace_id}).scalar_one()

    def current_class(self, workspace_id):
        return self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.school_class WHERE workspace_id=:w AND status='active')"), {"w": workspace_id}).scalar_one()

    def current_context(self, workspace_id):
        row = self._connection.execute(text("""SELECT c.class_id,c.term_id,c.name,t.name AS term_name,c.version
            FROM class_os.school_class c JOIN class_os.academic_term t ON t.workspace_id=c.workspace_id AND t.term_id=c.term_id
            WHERE c.workspace_id=:w AND c.status='active' AND t.status='active'"""), {"w": workspace_id}).mappings().one_or_none()
        return ClassView(**row) if row else None

    def class_context(self, workspace_id, class_id, term_id):
        return self._connection.execute(text("""SELECT c.version,c.status,t.status AS term_status FROM class_os.school_class c
            JOIN class_os.academic_term t ON t.workspace_id=c.workspace_id AND t.term_id=c.term_id
            WHERE c.workspace_id=:w AND c.class_id=:c AND c.term_id=:t"""),
            {"w": workspace_id, "c": class_id, "t": term_id}).mappings().one_or_none()

    def student_exists(self, workspace_id, student_id):
        return self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.student WHERE workspace_id=:w AND student_id=:s)"), {"w": workspace_id, "s": student_id}).scalar_one()

    def term_metadata(self, workspace_id, class_id, term_id):
        row = self._connection.execute(text("""SELECT c.class_id,t.term_id,t.name,t.start_date,t.end_date,t.version
            FROM class_os.school_class c JOIN class_os.academic_term t
            ON t.workspace_id=c.workspace_id AND t.term_id=c.term_id
            WHERE c.workspace_id=:w AND c.class_id=:c AND t.term_id=:t
            AND c.status='active' AND t.status='active'"""),
            {"w": workspace_id, "c": class_id, "t": term_id}).mappings().one_or_none()
        return TermMetadata(**row) if row else None

    def save_proposal(self, proposal, binding, payload, purpose):
        self._mutate(text("""INSERT INTO class_os.command_proposal
            (proposal_id,workspace_id,actor_id,session_digest,client_digest,csrf_digest,purpose,command_type,payload,payload_hash,risk,expires_at,state)
            VALUES(:proposal_id,:workspace_id,:actor_id,:session_digest,:client_digest,:csrf_digest,:purpose,:command_type,:payload,:hash,:risk,:expires_at,'draft')"""),
            {**binding, "proposal_id": proposal.proposal_id, "command_type": payload["command"], "payload": Jsonb(payload),
             "purpose": purpose,
             "hash": proposal.payload_hash, "risk": proposal.risk, "expires_at": proposal.expires_at})

    def proposal(self, workspace_id, proposal_id):
        return self._connection.execute(text("""SELECT proposal_id,workspace_id,actor_id,session_digest,client_digest,csrf_digest,
            payload,payload_hash,risk,expires_at,state,purpose FROM class_os.command_proposal
            WHERE workspace_id=:w AND proposal_id=:p"""), {"w": workspace_id, "p": proposal_id}).mappings().one_or_none()

    def approve(self, proposal_id, nonce_digest, now):
        self._mutate(text("""INSERT INTO class_os.approval_receipt(proposal_id,nonce_digest,approved_at)
            VALUES(:p,:nonce,:now) ON CONFLICT(proposal_id) DO UPDATE SET nonce_digest=EXCLUDED.nonce_digest,approved_at=EXCLUDED.approved_at"""),
            {"p": proposal_id, "nonce": nonce_digest, "now": now})
        self._mutate(text("UPDATE class_os.command_proposal SET state='approved' WHERE proposal_id=:p"), {"p": proposal_id})

    def approval(self, proposal_id):
        return self._connection.execute(text("SELECT nonce_digest,consumed_at FROM class_os.approval_receipt WHERE proposal_id=:p"), {"p": proposal_id}).mappings().one_or_none()

    def reject(self, proposal_id, now):
        self._mutate(text("UPDATE class_os.command_proposal SET state='rejected' WHERE proposal_id=:p"), {"p": proposal_id})
        self._consume_approval(proposal_id, now)

    def _consume_approval(self, proposal_id, now):
        # W1 has no approval row. An existing row must actually be consumed.
        expected = 1 if self.approval(proposal_id) is not None else 0
        self._mutate(text("UPDATE class_os.approval_receipt SET consumed_at=:now WHERE proposal_id=:p"),
                     {"p": proposal_id, "now": now}, expected=expected)

    def receipt(self, binding, key):
        row = self._connection.execute(text("""SELECT proposal_id,receipt_id,resource_id,resource_version
            FROM class_os.command_receipt WHERE workspace_id=:workspace_id AND actor_id=:actor_id AND idempotency_key=:key"""),
            {**binding, "key": key}).mappings().one_or_none()
        return {"proposal_id": row["proposal_id"], "receipt": Receipt(row["receipt_id"], row["resource_id"], row["resource_version"])} if row else None

    def apply(self, binding, command, now):
        if type(command) is ModelControl:
            return self.apply_model_configuration(binding, command, now)
        if type(command) is CreateExitExport:
            return self.create_exit(binding, command, now)
        if type(command) not in (CreateClass, CreateStudent):
            return self.apply_activity(binding, command, now)
        values = {**binding, "now": now, "class_id": command.class_id, "term_id": command.term_id, "name": command.name}
        if type(command) is CreateClass:
            self._mutate(text("""INSERT INTO class_os.academic_term
                (workspace_id,term_id,name,start_date,end_date,status,version,created_by,updated_by,created_at,updated_at)
                VALUES(:workspace_id,:term_id,:term_name,:start,:end,'active',1,:actor_id,:actor_id,:now,:now)"""),
                {**values, "term_name": command.term_name, "start": command.start_date, "end": command.end_date})
            self._mutate(text("""INSERT INTO class_os.school_class
                (workspace_id,class_id,term_id,name,status,version,created_by,updated_by,created_at,updated_at)
                VALUES(:workspace_id,:class_id,:term_id,:name,'active',1,:actor_id,:actor_id,:now,:now)"""), values)
            resource_id = command.class_id
        elif type(command) is CreateStudent:
            self._mutate(text("""INSERT INTO class_os.student
                (workspace_id,student_id,name,status,version,created_by,updated_by,created_at,updated_at)
                VALUES(:workspace_id,:student_id,:name,'active',1,:actor_id,:actor_id,:now,:now)"""),
                {**values, "student_id": command.student_id})
            self._mutate(text("""INSERT INTO class_os.enrollment
                (workspace_id,enrollment_id,student_id,class_id,term_id,valid_from,status,version,created_by,updated_by,created_at,updated_at)
                VALUES(:workspace_id,:enrollment_id,:student_id,:class_id,:term_id,:now,'active',1,:actor_id,:actor_id,:now,:now)"""),
                {**values, "student_id": command.student_id, "enrollment_id": uuid4()})
            resource_id = command.student_id
        else:
            raise ValueError("Unregistered roster mutation")
        return Receipt(uuid4(), resource_id, 1)

    def finish(self, binding, proposal_id, key, payload_hash, receipt, now):
        self._mutate(text("""INSERT INTO class_os.command_receipt
            (workspace_id,actor_id,idempotency_key,proposal_id,payload_hash,receipt_id,resource_id,resource_version,committed_at)
            VALUES(:workspace_id,:actor_id,:key,:p,:hash,:receipt,:resource,:version,:now)"""),
            {**binding, "key": key, "p": proposal_id, "hash": payload_hash, "receipt": receipt.receipt_id,
             "resource": receipt.resource_id, "version": receipt.version, "now": now})
        self._mutate(text("UPDATE class_os.command_proposal SET state='committed' WHERE proposal_id=:p"), {"p": proposal_id})
        self._consume_approval(proposal_id, now)

    def roster(self, workspace_id, class_id, term_id, now):
        rows = self._connection.execute(text("""SELECT s.student_id,s.name,s.version,s.status FROM class_os.student s
            JOIN class_os.enrollment e ON e.workspace_id=s.workspace_id AND e.student_id=s.student_id
            WHERE s.workspace_id=:w AND e.class_id=:c AND e.term_id=:t
            AND e.valid_from<=:now ORDER BY s.name,s.student_id"""),
            {"w": workspace_id, "c": class_id, "t": term_id, "now": now}).mappings()
        return tuple(StudentView(**row) for row in rows)

    def audit(self, binding, action, outcome, now, metadata):
        return self._store.audit(self._connection, binding, action, outcome, now, metadata)
