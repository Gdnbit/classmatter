"""Closed server orchestration metadata, no new tables or runtime grants."""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire','conversation.import.admit',
        'conversation.create','conversation.rename','conversation.archive','conversation.enqueue',
        'conversation.run.claim','conversation.run.finish','conversation.run.cancel','conversation.run.reconcile'));
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_run_risk_check CHECK(
        command_type NOT IN ('conversation.run.claim','conversation.run.finish','conversation.run.cancel','conversation.run.reconcile') OR risk='W1');
    """)


def downgrade():
    raise RuntimeError("Preserve run evidence; disable profile or forward-fix")
