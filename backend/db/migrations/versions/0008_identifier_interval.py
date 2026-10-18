"""Narrow interval closure for the existing W2 identifier replacement command."""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    # Never grant value/source/identity overwrite or DELETE.
    op.execute("GRANT UPDATE(valid_to) ON class_os.student_identifier TO class_os_runtime")


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
