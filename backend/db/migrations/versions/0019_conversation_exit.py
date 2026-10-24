"""D1-only v2 artifact and manual export; R1 remains pinned to0016."""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede',
        'task.create','task.update','task.complete','task.cancel','exit_export.create',
        'model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear','conversation_exit.create'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_check1;
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_d1_risk_check CHECK(
        (command_type IN ('conversation.control.initialize','conversation.clear','conversation_exit.create') AND risk='X') OR
        (command_type NOT IN ('conversation.control.initialize','conversation.clear','conversation_exit.create') AND risk IN ('W1','W2')));
    ALTER TABLE class_os.export_job DROP CONSTRAINT export_job_bundle_check;
    ALTER TABLE class_os.export_job ADD CHECK(
        bundle->>'schema_version' IN ('class-os.synthetic-core-exit.v1','classmatter.synthetic-exit.v2') AND octet_length(bundle::text)<=2097152);
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','command.status','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
        'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled','exit.summary','exit.download','audit.list',
        'model.config.read','model.test.started','model.test.completed','model.test.failed','model.enable','model.disable','model.invoke',
        'conversation.history','exit.conversation.summary','exit.conversation.download'));
    """)


def downgrade():
    raise RuntimeError("Keep restriction evidence; disable D1 profile or forward-fix, no destructive downgrade")
