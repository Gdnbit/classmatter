"""Minimal metadata-only Agent run audit through the existing Query Gateway."""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
        ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
        'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled'));""")


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
