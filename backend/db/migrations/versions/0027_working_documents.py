"""Explicit D2 documents. No default R1/D1 migration or application activation."""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.working_document (
        workspace_id uuid NOT NULL, document_id uuid NOT NULL, owner_id uuid NOT NULL,
        class_id uuid NOT NULL, term_id uuid NOT NULL,
        status varchar(16) NOT NULL CHECK(status IN ('draft','archived')),
        version integer NOT NULL CHECK(version>0),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        updated_at timestamptz NOT NULL CHECK(isfinite(updated_at) AND updated_at>=created_at),
        PRIMARY KEY(workspace_id,document_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id)
    );
    CREATE TABLE class_os.working_document_revision (
        workspace_id uuid NOT NULL, document_id uuid NOT NULL,
        version integer NOT NULL CHECK(version>0),
        status varchar(16) NOT NULL CHECK(status IN ('draft','archived')),
        title varchar(80) NOT NULL CHECK(title=btrim(title) AND title<>'' AND title !~ '[[:cntrl:]]'),
        body text NOT NULL CHECK(char_length(body)<=100000 AND octet_length(body)<=400000),
        format varchar(16) NOT NULL CHECK(format IN ('plain-text','markdown')),
        operation varchar(24) NOT NULL CHECK(operation IN
            ('document.create','document.revise','document.archive','document.restore')),
        created_by uuid NOT NULL, created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        PRIMARY KEY(workspace_id,document_id,version),
        FOREIGN KEY(workspace_id,document_id) REFERENCES class_os.working_document(workspace_id,document_id),
        FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id),
        UNIQUE(workspace_id,document_id,version,status)
    );
    ALTER TABLE class_os.working_document ADD CONSTRAINT working_document_current_revision
        FOREIGN KEY(workspace_id,document_id,version,status)
        REFERENCES class_os.working_document_revision(workspace_id,document_id,version,status)
        DEFERRABLE INITIALLY DEFERRED;
    CREATE INDEX working_document_list ON class_os.working_document
        (workspace_id,owner_id,class_id,term_id,updated_at,document_id);
    REVOKE ALL ON class_os.working_document,class_os.working_document_revision FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.working_document,class_os.working_document_revision TO class_os_runtime;
    GRANT UPDATE(status,version,updated_at) ON class_os.working_document TO class_os_runtime;
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire','conversation.import.admit',
        'conversation.create','conversation.rename','conversation.archive','conversation.enqueue',
        'conversation.run.claim','conversation.run.finish','conversation.run.cancel','conversation.run.reconcile','conversation.run.finish-result',
        'document.create','document.revise','document.archive','document.restore'));
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_document_risk_check
        CHECK(command_type NOT IN ('document.create','document.revise','document.archive','document.restore') OR risk='W2');
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','command.status','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
        'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled','exit.summary','exit.download','audit.list',
        'model.config.read','model.test.started','model.test.completed','model.test.failed','model.enable','model.disable','model.invoke',
        'conversation.history','exit.conversation.summary','exit.conversation.download','conversation.transfer.proof',
        'document.list','document.read','document.history'));
    """)


def downgrade():
    raise RuntimeError("Preserve document revisions; restore a verified full backup or forward-fix")
