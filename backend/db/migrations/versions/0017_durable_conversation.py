"""Explicit post-R1 synthetic conversation profile; never the R1 default."""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.enrollment ADD CONSTRAINT conversation_enrollment_scope
        UNIQUE(workspace_id,class_id,term_id,student_id,enrollment_id);
    CREATE TABLE class_os.conversation_thread (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, owner_id uuid NOT NULL,
        class_id uuid NOT NULL, term_id uuid NOT NULL, student_id uuid, enrollment_id uuid,
        title varchar(80) NOT NULL CHECK(title ~ '[^[:space:]]' AND title !~ '[[:cntrl:]]'),
        status varchar(16) NOT NULL CHECK(status IN ('active','archived','cleared')),
        version integer NOT NULL CHECK(version>0),
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL CHECK(updated_at>=created_at),
        cleared_at timestamptz,
        PRIMARY KEY(workspace_id,thread_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id),
        CHECK((student_id IS NULL)=(enrollment_id IS NULL)),
        FOREIGN KEY(workspace_id,class_id,term_id,student_id,enrollment_id)
            REFERENCES class_os.enrollment(workspace_id,class_id,term_id,student_id,enrollment_id),
        CHECK((status='cleared' AND cleared_at IS NOT NULL AND cleared_at>=created_at
               AND updated_at>=cleared_at AND title='已清除的会话') OR (status<>'cleared' AND cleared_at IS NULL))
    );
    CREATE INDEX conversation_thread_list ON class_os.conversation_thread(workspace_id,owner_id,class_id,term_id,updated_at,thread_id);
    CREATE TABLE class_os.conversation_turn (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL,
        ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 10000),
        client_request_id uuid NOT NULL, request_hash varchar(64) NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
        mode varchar(8) NOT NULL CHECK(mode IN ('read','draft','chat')),
        draft_kind varchar(16) NOT NULL CHECK(draft_kind IN ('task','record-note')),
        created_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,thread_id,turn_id),
        UNIQUE(workspace_id,thread_id,ordinal), UNIQUE(workspace_id,thread_id,client_request_id),
        FOREIGN KEY(workspace_id,thread_id) REFERENCES class_os.conversation_thread(workspace_id,thread_id)
    );
    CREATE TABLE class_os.conversation_message (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL, message_id uuid NOT NULL,
        role varchar(16) NOT NULL, origin varchar(32) NOT NULL,
        visibility varchar(16) NOT NULL CHECK(visibility IN ('visible','restricted')),
        body text, created_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,thread_id,message_id), UNIQUE(workspace_id,thread_id,turn_id,role),
        FOREIGN KEY(workspace_id,thread_id,turn_id) REFERENCES class_os.conversation_turn(workspace_id,thread_id,turn_id),
        CHECK((role='user' AND origin='user-original') OR (role='assistant' AND origin='assistant-unverified')),
        CHECK((visibility='restricted' AND body IS NULL) OR
              (visibility='visible' AND body IS NOT NULL AND body ~ '[^[:space:]]'
               AND length(body)<=8000 AND octet_length(body)<=16000 AND (role<>'user' OR length(body)<=2000)))
    );
    CREATE TABLE class_os.conversation_run (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL, run_id uuid NOT NULL,
        state varchar(20) NOT NULL CHECK(state IN ('queued','running','cancel_requested','completed','failed','cancelled','interrupted','unknown')),
        version integer NOT NULL CHECK(version>0),
        created_at timestamptz NOT NULL, queued_until timestamptz NOT NULL,
        generation uuid, started_at timestamptz, lease_until timestamptz, ended_at timestamptz, cancel_requested_at timestamptz,
        input_tokens integer CHECK(input_tokens>=0), output_tokens integer CHECK(output_tokens>=0), duration_ms integer CHECK(duration_ms>=0),
        PRIMARY KEY(workspace_id,thread_id,run_id), UNIQUE(workspace_id,thread_id,turn_id),
        FOREIGN KEY(workspace_id,thread_id,turn_id) REFERENCES class_os.conversation_turn(workspace_id,thread_id,turn_id),
        CHECK(queued_until>created_at AND queued_until<=created_at+interval '5 minutes'),
        CHECK((state='queued' AND generation IS NULL AND started_at IS NULL AND lease_until IS NULL
               AND ended_at IS NULL AND cancel_requested_at IS NULL) OR
              (state='cancelled' AND generation IS NULL AND started_at IS NULL AND lease_until IS NULL
               AND cancel_requested_at IS NULL AND ended_at IS NOT NULL AND ended_at>=created_at) OR
              (state<>'queued' AND generation IS NOT NULL AND started_at IS NOT NULL AND lease_until IS NOT NULL
               AND started_at>=created_at AND started_at<queued_until AND lease_until>started_at
               AND lease_until<=started_at+interval '5 minutes'
               AND ((state IN ('running','cancel_requested') AND ended_at IS NULL) OR
                    (state IN ('completed','failed','cancelled','unknown') AND ended_at IS NOT NULL
                     AND ended_at>=started_at AND ended_at<lease_until) OR
                    (state='interrupted' AND ended_at IS NOT NULL AND ended_at>=lease_until))
               AND (cancel_requested_at IS NULL OR (cancel_requested_at>=started_at AND cancel_requested_at<lease_until
                    AND (ended_at IS NULL OR ended_at>=cancel_requested_at)))
               AND (state<>'cancel_requested' OR cancel_requested_at IS NOT NULL)
               AND (state NOT IN ('running','completed') OR cancel_requested_at IS NULL))),
        CHECK(state NOT IN ('queued','running','cancel_requested') OR
              (input_tokens IS NULL AND output_tokens IS NULL AND duration_ms IS NULL))
    );
    CREATE UNIQUE INDEX conversation_active_run ON class_os.conversation_run(workspace_id,thread_id)
        WHERE state IN ('queued','running','cancel_requested');
    GRANT SELECT,INSERT ON class_os.conversation_thread,class_os.conversation_turn,
        class_os.conversation_message,class_os.conversation_run TO class_os_runtime;
    GRANT UPDATE(title,status,version,updated_at,cleared_at) ON class_os.conversation_thread TO class_os_runtime;
    GRANT UPDATE(body,visibility) ON class_os.conversation_message TO class_os_runtime;
    GRANT UPDATE(state,version,generation,started_at,lease_until,ended_at,cancel_requested_at,input_tokens,output_tokens,duration_ms)
        ON class_os.conversation_run TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Disable the profile and use a verified snapshot or forward-fix; no destructive downgrade")
