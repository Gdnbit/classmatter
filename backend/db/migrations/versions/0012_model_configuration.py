"""Protected model credentials, fixed metadata and explicit control audit actions."""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.model_configuration (
        workspace_id uuid PRIMARY KEY REFERENCES class_os.workspace(workspace_id),
        candidate_id uuid NOT NULL, version integer NOT NULL CHECK(version>0),
        protocol text CHECK(protocol IN ('chat-completions','responses')),
        model text CHECK(length(model) BETWEEN 1 AND 128), base_url text CHECK(length(base_url) BETWEEN 1 AND 512),
        sealed bytea CHECK(octet_length(sealed) BETWEEN 1 AND 16384), updated_at timestamptz NOT NULL,
        CHECK((sealed IS NULL AND protocol IS NULL AND model IS NULL AND base_url IS NULL)
           OR (sealed IS NOT NULL AND protocol IS NOT NULL AND model IS NOT NULL AND base_url IS NOT NULL))
    );
    REVOKE ALL ON class_os.model_configuration FROM PUBLIC;
    GRANT SELECT,INSERT,UPDATE ON class_os.model_configuration TO class_os_runtime;
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','student.create','student.update_identifier','student.deactivate',
        'record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel','exit_export.create',
        'model_configuration.save','model_configuration.clear'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_purpose_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(purpose IN ('manage-roster','manage-class','exit-recovery','manage-model'));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_purpose_check;
    ALTER TABLE class_os.business_audit ADD CHECK(purpose IN ('manage-roster','manage-class','exit-recovery','manage-model'));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','command.status','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
        'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled','exit.summary','exit.download','audit.list',
        'model.config.read','model.test.started','model.test.completed','model.test.failed','model.enable','model.disable','model.invoke'));
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
