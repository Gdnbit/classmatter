"""Controlled synthetic core exit artifact; not lifecycle-complete release."""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_purpose_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(purpose IN ('manage-roster','manage-class','exit-recovery'));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_purpose_check;
    ALTER TABLE class_os.business_audit ADD CHECK(purpose IN ('manage-roster','manage-class','exit-recovery'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','student.create','student.update_identifier','student.deactivate',
        'record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel','exit_export.create'));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
        'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled','exit.summary','exit.download'));
    CREATE TABLE class_os.export_job (
        workspace_id uuid NOT NULL, export_id uuid NOT NULL, actor_id uuid NOT NULL,
        package_hash char(64) NOT NULL, bundle jsonb NOT NULL,
        created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL CHECK(expires_at>created_at),
        state varchar(16) NOT NULL CHECK(state IN ('ready','expired')),
        PRIMARY KEY(workspace_id,export_id),
        CHECK(bundle->>'schema_version'='class-os.synthetic-core-exit.v1' AND octet_length(bundle::text)<=2097152),
        FOREIGN KEY(workspace_id,actor_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    GRANT SELECT,INSERT ON class_os.export_job TO class_os_runtime;
    GRANT SELECT(workspace_id,event_id,actor_id,purpose,action,outcome,occurred_at,proposal_id,payload_hash,receipt_id,resource_id,resource_version,class_id,term_id)
        ON class_os.business_audit TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
