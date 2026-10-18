"""Closed name-correction command allowlist and its one-column write grant."""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede',
        'task.create','task.update','task.complete','task.cancel','exit_export.create',
        'model_configuration.save','model_configuration.clear'));
    GRANT UPDATE(name) ON class_os.student TO class_os_runtime;
    """)


def downgrade():
    # Old code cannot decode new persisted proposals; never delete those to
    # make a down-migration appear successful. Use verified snapshot/forward fix.
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
