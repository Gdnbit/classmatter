"""Initial deployment metadata; no business aggregate or owner creation."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "database_state",
        sa.Column("singleton", sa.Boolean(), primary_key=True),
        sa.Column("data_mode", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("singleton = true", name="database_state_singleton"),
        sa.CheckConstraint("data_mode = 'synthetic-only'", name="database_state_synthetic_only"),
        schema="class_os",
    )
    op.execute("INSERT INTO class_os.database_state(singleton, data_mode) VALUES(true, 'synthetic-only')")
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA class_os TO class_os_runtime")
    op.execute("GRANT SELECT ON class_os.database_state TO class_os_runtime")


def downgrade():
    raise RuntimeError("Destructive downgrade is not supported; restore a verified snapshot or forward-fix")
