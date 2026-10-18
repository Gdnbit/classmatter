"""Fixed R1 identifiers, immutable record revisions and manual tasks."""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','student.create','student.update_identifier','student.deactivate',
        'record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_purpose_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(purpose IN ('manage-roster','manage-class'));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_purpose_check;
    ALTER TABLE class_os.business_audit ADD CHECK(purpose IN ('manage-roster','manage-class'));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline'));
    CREATE TABLE class_os.student_identifier (
        workspace_id uuid NOT NULL, identifier_id uuid NOT NULL, student_id uuid NOT NULL,
        authority varchar(80) NOT NULL, identifier_type varchar(24) NOT NULL CHECK(identifier_type IN ('school_number','exam_number')),
        value varchar(80) NOT NULL, valid_from timestamptz NOT NULL, valid_to timestamptz,
        created_by uuid NOT NULL, created_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,identifier_id), CHECK(valid_to IS NULL OR valid_to>valid_from),
        FOREIGN KEY(workspace_id,student_id) REFERENCES class_os.student(workspace_id,student_id),
        FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE INDEX identifier_lookup ON class_os.student_identifier(workspace_id,authority,identifier_type,value);
    CREATE TABLE class_os.record_revision (
        workspace_id uuid NOT NULL, record_id uuid NOT NULL, version integer NOT NULL CHECK(version>0),
        class_id uuid NOT NULL, term_id uuid NOT NULL, student_id uuid NOT NULL,
        kind varchar(32) NOT NULL CHECK(kind IN ('attendance_late_fact','attendance_absent_fact','leave_requested_fact',
            'leave_approved_fact','leave_returned_fact','homework_missing_fact','homework_submitted_fact','ordinary_fact',
            'teacher_observation','discipline_fact','conversation_fact')),
        occurred_at timestamptz NOT NULL, recorded_at timestamptz NOT NULL, recorded_by uuid NOT NULL,
        fact_text varchar(2000) NOT NULL, observation_text varchar(2000) NOT NULL,
        source varchar(32) NOT NULL CHECK(source='trusted-ui-synthetic'), related_record_id uuid,
        revision_kind varchar(24) NOT NULL CHECK(revision_kind IN ('create','correct','supersede')),
        revision_reason varchar(500) NOT NULL,
        PRIMARY KEY(workspace_id,record_id,version),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id),
        FOREIGN KEY(workspace_id,student_id) REFERENCES class_os.student(workspace_id,student_id),
        FOREIGN KEY(workspace_id,recorded_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE INDEX record_timeline ON class_os.record_revision(workspace_id,class_id,term_id,student_id,occurred_at);
    CREATE TABLE class_os.manual_task (
        workspace_id uuid NOT NULL, task_id uuid NOT NULL, class_id uuid NOT NULL, term_id uuid NOT NULL,
        title varchar(80) NOT NULL, student_id uuid, source_record_id uuid, due_at timestamptz,
        status varchar(16) NOT NULL CHECK(status IN ('not-started','in-progress','waiting','done','cancelled')),
        evidence varchar(500) NOT NULL, version integer NOT NULL CHECK(version>0),
        created_by uuid NOT NULL, updated_by uuid NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,task_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id),
        FOREIGN KEY(workspace_id,student_id) REFERENCES class_os.student(workspace_id,student_id),
        FOREIGN KEY(workspace_id,created_by) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,updated_by) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    GRANT SELECT,INSERT ON class_os.student_identifier,class_os.record_revision,class_os.manual_task TO class_os_runtime;
    GRANT UPDATE(name,status,version,updated_by,updated_at) ON class_os.school_class TO class_os_runtime;
    GRANT UPDATE(status,version,updated_by,updated_at) ON class_os.academic_term,class_os.student TO class_os_runtime;
    GRANT UPDATE(status,valid_to,version,updated_by,updated_at) ON class_os.enrollment TO class_os_runtime;
    GRANT UPDATE(status,evidence,version,updated_by,updated_at) ON class_os.manual_task TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
