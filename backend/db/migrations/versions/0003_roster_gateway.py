"""First fixed roster commands plus BCG/QG transaction metadata, synthetic only."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.owner_account ADD CONSTRAINT owner_workspace_key UNIQUE(workspace_id, owner_id);
    CREATE TABLE class_os.academic_term (
        workspace_id uuid NOT NULL REFERENCES class_os.workspace(workspace_id),
        term_id uuid NOT NULL, name varchar(80) NOT NULL,
        start_date date NOT NULL, end_date date NOT NULL CHECK(end_date>start_date),
        status varchar(16) NOT NULL CHECK(status IN ('active','archived')),
        version integer NOT NULL CHECK(version>0),
        created_by uuid NOT NULL, updated_by uuid NOT NULL,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id, term_id),
        FOREIGN KEY(workspace_id, created_by) REFERENCES class_os.owner_account(workspace_id, owner_id),
        FOREIGN KEY(workspace_id, updated_by) REFERENCES class_os.owner_account(workspace_id, owner_id)
    );
    CREATE UNIQUE INDEX current_term ON class_os.academic_term(workspace_id) WHERE status='active';
    CREATE TABLE class_os.school_class (
        workspace_id uuid NOT NULL, class_id uuid NOT NULL, term_id uuid NOT NULL,
        name varchar(80) NOT NULL, status varchar(16) NOT NULL CHECK(status IN ('active','archived')),
        version integer NOT NULL CHECK(version>0),
        created_by uuid NOT NULL, updated_by uuid NOT NULL,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,class_id), UNIQUE(workspace_id,class_id,term_id),
        FOREIGN KEY(workspace_id,term_id) REFERENCES class_os.academic_term(workspace_id,term_id),
        FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,updated_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE UNIQUE INDEX current_class ON class_os.school_class(workspace_id) WHERE status='active';
    CREATE TABLE class_os.student (
        workspace_id uuid NOT NULL REFERENCES class_os.workspace(workspace_id), student_id uuid NOT NULL,
        name varchar(80) NOT NULL, status varchar(16) NOT NULL CHECK(status IN ('active','inactive')),
        version integer NOT NULL CHECK(version>0),
        created_by uuid NOT NULL, updated_by uuid NOT NULL,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,student_id),
        FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,updated_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE TABLE class_os.enrollment (
        workspace_id uuid NOT NULL, enrollment_id uuid NOT NULL, student_id uuid NOT NULL,
        class_id uuid NOT NULL, term_id uuid NOT NULL, valid_from timestamptz NOT NULL, valid_to timestamptz,
        status varchar(16) NOT NULL CHECK(status IN ('active','inactive')),
        version integer NOT NULL CHECK(version>0),
        created_by uuid NOT NULL, updated_by uuid NOT NULL,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,enrollment_id), CHECK(valid_to IS NULL OR valid_to>valid_from),
        FOREIGN KEY(workspace_id,student_id) REFERENCES class_os.student(workspace_id,student_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id),
        FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,updated_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE UNIQUE INDEX current_enrollment ON class_os.enrollment(workspace_id,student_id) WHERE valid_to IS NULL AND status='active';
    CREATE TABLE class_os.command_proposal (
        proposal_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, actor_id uuid NOT NULL,
        session_digest char(64) NOT NULL, client_digest char(64) NOT NULL, csrf_digest char(64) NOT NULL,
        purpose varchar(32) NOT NULL CHECK(purpose='manage-roster'),
        command_type varchar(32) NOT NULL CHECK(command_type IN ('class.create','student.create')),
        payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object' AND payload->>'command'=command_type),
        payload_hash char(64) NOT NULL, risk varchar(8) NOT NULL CHECK(risk IN ('W1','W2')),
        expires_at timestamptz NOT NULL, state varchar(16) NOT NULL CHECK(state IN ('draft','approved','rejected','committed')),
        FOREIGN KEY(workspace_id,actor_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE TABLE class_os.approval_receipt (
        proposal_id uuid PRIMARY KEY REFERENCES class_os.command_proposal(proposal_id),
        nonce_digest char(64) NOT NULL, approved_at timestamptz NOT NULL, consumed_at timestamptz
    );
    CREATE TABLE class_os.command_receipt (
        workspace_id uuid NOT NULL, actor_id uuid NOT NULL, idempotency_key uuid NOT NULL,
        proposal_id uuid NOT NULL UNIQUE REFERENCES class_os.command_proposal(proposal_id),
        payload_hash char(64) NOT NULL, receipt_id uuid NOT NULL UNIQUE, resource_id uuid NOT NULL,
        resource_version integer NOT NULL CHECK(resource_version>0), committed_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,actor_id,idempotency_key),
        FOREIGN KEY(workspace_id,actor_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE TABLE class_os.business_audit (
        event_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, actor_id uuid NOT NULL,
        session_digest char(64) NOT NULL, purpose varchar(32) NOT NULL CHECK(purpose='manage-roster'),
        action varchar(32) NOT NULL CHECK(action IN ('command.preview','command.approve','command.reject','command.commit','roster.list','class.context')),
        outcome varchar(16) NOT NULL CHECK(outcome IN ('allowed','denied')), occurred_at timestamptz NOT NULL,
        proposal_id uuid, payload_hash char(64), receipt_id uuid, resource_id uuid, resource_version integer,
        class_id uuid, term_id uuid,
        FOREIGN KEY(workspace_id,actor_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    GRANT SELECT,INSERT ON class_os.academic_term,class_os.school_class,class_os.student,class_os.enrollment TO class_os_runtime;
    GRANT SELECT,INSERT,UPDATE ON class_os.command_proposal,class_os.approval_receipt TO class_os_runtime;
    GRANT SELECT,INSERT ON class_os.command_receipt TO class_os_runtime;
    GRANT INSERT ON class_os.business_audit TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
