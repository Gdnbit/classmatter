"""Closed human interaction command metadata; no new table or role access."""
from alembic import op

revision = "0024"
down_revision = "0023"
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
        'conversation.create','conversation.rename','conversation.archive','conversation.enqueue'));
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_interaction_risk_check CHECK(
        command_type NOT IN ('conversation.create','conversation.rename','conversation.archive','conversation.enqueue') OR risk='W1');
    """)


def downgrade():
    raise RuntimeError("Preserve interaction receipts and restriction evidence; disable profile or forward-fix")
