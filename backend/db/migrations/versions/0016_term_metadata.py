"""Closed Term metadata correction, with only the three required column grants."""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede',
        'task.create','task.update','task.complete','task.cancel','exit_export.create',
        'model_configuration.save','model_configuration.clear'));
    GRANT UPDATE(name,start_date,end_date) ON class_os.academic_term TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
