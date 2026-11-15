"""Source-bound built-in summary attempts; no new Agent business authority."""
from alembic import op

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE class_os.builtin_summary_attempt (
        workspace_id uuid NOT NULL, owner_id uuid NOT NULL,
        class_id uuid NOT NULL, term_id uuid NOT NULL,
        program_id uuid NOT NULL, program_version smallint NOT NULL CHECK(program_version=1),
        thread_id uuid NOT NULL, request_id uuid NOT NULL,
        basis_hash varchar(64) NOT NULL CHECK(basis_hash ~ '^[a-f0-9]{64}$'),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        PRIMARY KEY(workspace_id,program_id,basis_hash),
        UNIQUE(workspace_id,thread_id,request_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id),
        FOREIGN KEY(workspace_id,thread_id,request_id)
          REFERENCES class_os.workspace_chat_turn(workspace_id,thread_id,request_id)
      );
      GRANT SELECT,INSERT ON class_os.builtin_summary_attempt TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError('Preserve built-in work history; restore a verified checkpoint or forward-fix')
