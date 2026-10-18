"""Only fixed title/deadline columns for the existing manual Task update."""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("GRANT UPDATE(title,due_at) ON class_os.manual_task TO class_os_runtime")


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
