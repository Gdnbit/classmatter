"""D4-only factual chat comparisons; no change to command authority or R1."""
from alembic import op

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''ALTER TABLE class_os.workspace_chat_turn ADD COLUMN change_preview jsonb
      CHECK(change_preview IS NULL OR (candidate IS NOT NULL AND state='completed'
        AND jsonb_typeof(change_preview)='object' AND octet_length(change_preview::text)<=900000));
      GRANT UPDATE(change_preview) ON class_os.workspace_chat_turn TO class_os_runtime;''')


def downgrade():
    raise RuntimeError('Preserve historical comparisons; restore the verified pre-upgrade checkpoint')
