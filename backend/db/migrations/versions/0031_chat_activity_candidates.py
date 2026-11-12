"""D4 conversational activity candidates; existing BCG remains the sole writer."""
from alembic import op

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE class_os.workspace_chat_turn DROP CONSTRAINT workspace_chat_candidate_command_check;
      ALTER TABLE class_os.workspace_chat_turn ADD CONSTRAINT workspace_chat_candidate_command_check
      CHECK(candidate IS NULL OR (jsonb_typeof(candidate)='object' AND octet_length(candidate::text)<=440000
        AND candidate->>'command' IN ('class.create','class.update','term.update','student.create','student.update_name',
        'record.create','task.create','task.update','task.complete','task.cancel','document.create','document.revise',
        'exam.create','score.record','seat.layout.create','seat.assign','seat.swap')))
    """)


def downgrade():
    raise RuntimeError('Preserve activity candidates and receipts; restore the verified checkpoint or forward-fix')
