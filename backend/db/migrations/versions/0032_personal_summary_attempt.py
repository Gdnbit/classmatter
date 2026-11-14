"""One source-bound personal summary program; no Agent business writer."""
from alembic import op

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE class_os.personal_summary_attempt (
        workspace_id uuid NOT NULL, owner_id uuid NOT NULL,
        document_id uuid NOT NULL, document_version integer NOT NULL CHECK(document_version>0),
        thread_id uuid NOT NULL, request_id uuid NOT NULL,
        waiting_request_id uuid,
        basis_hash varchar(64) NOT NULL CHECK(basis_hash ~ '^[a-f0-9]{64}$'),
        answer_required boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        PRIMARY KEY(workspace_id,document_id,basis_hash),
        UNIQUE(workspace_id,thread_id,request_id),
        UNIQUE(workspace_id,thread_id,waiting_request_id),
        CHECK(answer_required=(waiting_request_id IS NOT NULL)),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,document_id,document_version)
          REFERENCES class_os.working_document_revision(workspace_id,document_id,version),
        FOREIGN KEY(workspace_id,thread_id,request_id)
          REFERENCES class_os.workspace_chat_turn(workspace_id,thread_id,request_id),
        FOREIGN KEY(workspace_id,thread_id,waiting_request_id)
          REFERENCES class_os.workspace_chat_turn(workspace_id,thread_id,request_id)
      );
      REVOKE ALL ON class_os.personal_summary_attempt FROM PUBLIC;
      GRANT SELECT,INSERT ON class_os.personal_summary_attempt TO class_os_runtime;
      GRANT UPDATE(answer_required,waiting_request_id) ON class_os.personal_summary_attempt TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError('Preserve delegation and initiative history; restore a verified checkpoint or forward-fix')
