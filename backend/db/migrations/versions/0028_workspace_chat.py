"""Explicit D3 workspace interaction storage; no changes to D1 scope semantics."""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.workspace_chat_thread (
      workspace_id uuid NOT NULL, thread_id uuid NOT NULL, owner_id uuid NOT NULL,
      title varchar(80) NOT NULL CHECK(title=btrim(title) AND title<>'' AND title !~ '[[:cntrl:]]'),
      status varchar(16) NOT NULL CHECK(status IN ('active','archived','cleared')),
      version integer NOT NULL CHECK(version>0),
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      updated_at timestamptz NOT NULL CHECK(isfinite(updated_at) AND updated_at>=created_at),
      cleared_at timestamptz CHECK(cleared_at IS NULL OR isfinite(cleared_at)),
      PRIMARY KEY(workspace_id,thread_id),
      FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
      CHECK((status='cleared')=(cleared_at IS NOT NULL))
    );
    CREATE TABLE class_os.workspace_chat_turn (
      workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL, request_id uuid NOT NULL,
      ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 10000),
      input_hash varchar(64) NOT NULL CHECK(input_hash ~ '^[a-f0-9]{64}$'),
      user_text text CHECK(user_text IS NULL OR (char_length(user_text) BETWEEN 1 AND 2000 AND octet_length(user_text)<=8000)),
      assistant_text text CHECK(assistant_text IS NULL OR (char_length(assistant_text) BETWEEN 1 AND 4000 AND octet_length(assistant_text)<=16000)),
      candidate jsonb, candidate_hash varchar(64),
      state varchar(16) NOT NULL CHECK(state IN ('queued','running','completed','failed','cancelled','unknown')),
      version integer NOT NULL CHECK(version>0), generation uuid,
      created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
      started_at timestamptz CHECK(started_at IS NULL OR isfinite(started_at)),
      lease_until timestamptz CHECK(lease_until IS NULL OR isfinite(lease_until)),
      ended_at timestamptz CHECK(ended_at IS NULL OR isfinite(ended_at)),
      input_tokens integer CHECK(input_tokens>=0), output_tokens integer CHECK(output_tokens>=0),
      duration_ms integer CHECK(duration_ms>=0),
      PRIMARY KEY(workspace_id,thread_id,turn_id),
      UNIQUE(workspace_id,thread_id,request_id), UNIQUE(workspace_id,thread_id,ordinal),
      FOREIGN KEY(workspace_id,thread_id) REFERENCES class_os.workspace_chat_thread(workspace_id,thread_id),
      CHECK((candidate IS NULL)=(candidate_hash IS NULL)),
      CHECK(candidate_hash IS NULL OR candidate_hash ~ '^[a-f0-9]{64}$'),
      CHECK(candidate IS NULL OR (jsonb_typeof(candidate)='object' AND octet_length(candidate::text)<=440000
        AND candidate->>'command' IN ('class.create','class.update','term.update','student.create','student.update_name',
                                      'task.create','task.update','document.create','document.revise'))),
      CHECK(state='completed' OR (assistant_text IS NULL AND candidate IS NULL)),
      CHECK((state IN ('queued','running'))=(ended_at IS NULL)),
      CHECK(state<>'queued' OR (generation IS NULL AND started_at IS NULL AND lease_until IS NULL)),
      CHECK(started_at IS NULL OR (generation IS NOT NULL AND started_at>=created_at
        AND lease_until>started_at AND lease_until<=started_at+interval '5 minutes'))
    );
    CREATE UNIQUE INDEX workspace_chat_one_active ON class_os.workspace_chat_turn(workspace_id,thread_id)
      WHERE state IN ('queued','running');
    CREATE INDEX workspace_chat_thread_list ON class_os.workspace_chat_thread(workspace_id,owner_id,updated_at,thread_id);
    CREATE TABLE class_os.workspace_chat_audit (
      workspace_id uuid NOT NULL, event_id uuid NOT NULL, owner_id uuid NOT NULL,
      action varchar(40) NOT NULL CHECK(action IN ('workspace.chat.send','workspace.chat.claim','workspace.chat.finish',
        'workspace.chat.cancel','workspace.chat.clear','workspace.chat.archive','workspace.chat.list','workspace.chat.read')),
      outcome varchar(8) NOT NULL CHECK(outcome IN ('allowed','denied')),
      resource_id uuid, resource_version integer CHECK(resource_version>0),
      occurred_at timestamptz NOT NULL CHECK(isfinite(occurred_at)),
      PRIMARY KEY(workspace_id,event_id),
      FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    REVOKE ALL ON class_os.workspace_chat_thread,class_os.workspace_chat_turn,class_os.workspace_chat_audit FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.workspace_chat_thread,class_os.workspace_chat_turn,class_os.workspace_chat_audit TO class_os_runtime;
    GRANT UPDATE(title,status,version,updated_at,cleared_at) ON class_os.workspace_chat_thread TO class_os_runtime;
    GRANT UPDATE(user_text,assistant_text,candidate,candidate_hash,state,version,generation,started_at,lease_until,ended_at,
      input_tokens,output_tokens,duration_ms) ON class_os.workspace_chat_turn TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Preserve chat history; use a verified full backup or forward-fix")
