"""Human source retirement reuses proposal, receipt and audit tables."""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_d1_risk_check;
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_d1_risk_check CHECK(
        (command_type IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal',
                         'conversation.import.stage','conversation.transfer.retire') AND risk='X') OR
        (command_type NOT IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal',
                             'conversation.import.stage','conversation.transfer.retire') AND risk IN ('W1','W2')));
    """)


def downgrade():
    raise RuntimeError("Preserve retirement evidence; disable profile or forward-fix")
