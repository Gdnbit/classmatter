"""Bounded bilateral material collection; no remote business-command surface."""
from alembic import op

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE class_os.collaboration_identity (
        workspace_id uuid PRIMARY KEY, owner_id uuid NOT NULL,
        public_key varchar(64) NOT NULL CHECK(public_key ~ '^[a-f0-9]{64}$'),
        sealed_key bytea NOT NULL CHECK(octet_length(sealed_key) BETWEEN 32 AND 16384),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
      );
      CREATE TABLE class_os.collaboration_peer (
        workspace_id uuid NOT NULL, owner_id uuid NOT NULL, peer_id uuid NOT NULL,
        name varchar(80) NOT NULL CHECK(length(name)>0), endpoint varchar(128) NOT NULL,
        public_key varchar(64) NOT NULL CHECK(public_key ~ '^[a-f0-9]{64}$'),
        class_id uuid NOT NULL, term_id uuid NOT NULL,
        status varchar(10) NOT NULL CHECK(status IN ('active','revoked')),
        version integer NOT NULL CHECK(version>0), created_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,peer_id), CHECK(workspace_id<>peer_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id)
      );
      CREATE TABLE class_os.collaboration_message (
        workspace_id uuid NOT NULL, owner_id uuid NOT NULL, message_id uuid NOT NULL,
        request_id uuid NOT NULL, peer_id uuid NOT NULL,
        direction varchar(8) NOT NULL CHECK(direction IN ('incoming','outgoing')),
        operation varchar(8) NOT NULL CHECK(operation IN ('request','material')),
        title varchar(80) NOT NULL CHECK(length(title)>0), body text NOT NULL CHECK(length(body) BETWEEN 1 AND 12000),
        source_document_id uuid, source_version integer CHECK(source_version>0),
        class_id uuid NOT NULL, term_id uuid NOT NULL, thread_id uuid NOT NULL,
        payload_hash varchar(64) NOT NULL CHECK(payload_hash ~ '^[a-f0-9]{64}$'),
        attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 12),
        next_attempt_at timestamptz NOT NULL, delivered_at timestamptz,
        last_error varchar(16) CHECK(last_error IN ('offline','rejected','invalid-receipt')),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        PRIMARY KEY(workspace_id,message_id),
        UNIQUE(workspace_id,request_id,operation,direction),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,peer_id) REFERENCES class_os.collaboration_peer(workspace_id,peer_id),
        FOREIGN KEY(workspace_id,class_id,term_id) REFERENCES class_os.school_class(workspace_id,class_id,term_id),
        FOREIGN KEY(workspace_id,thread_id) REFERENCES class_os.workspace_chat_thread(workspace_id,thread_id),
        CHECK((operation='request' AND message_id=request_id AND source_document_id IS NULL AND source_version IS NULL)
          OR (operation='material' AND message_id<>request_id AND source_document_id IS NOT NULL AND source_version IS NOT NULL)),
        CHECK(direction='outgoing' OR delivered_at IS NOT NULL)
      );
      CREATE TABLE class_os.collaboration_summary (
        workspace_id uuid NOT NULL, owner_id uuid NOT NULL, request_id uuid NOT NULL,
        source_message_id uuid NOT NULL, document_id uuid NOT NULL, document_version integer NOT NULL CHECK(document_version>0),
        body_hash varchar(64) NOT NULL CHECK(body_hash ~ '^[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
        PRIMARY KEY(workspace_id,request_id), UNIQUE(workspace_id,source_message_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id),
        FOREIGN KEY(workspace_id,source_message_id) REFERENCES class_os.collaboration_message(workspace_id,message_id),
        FOREIGN KEY(workspace_id,document_id,document_version)
          REFERENCES class_os.working_document_revision(workspace_id,document_id,version)
      );
      CREATE TABLE class_os.collaboration_audit (
        workspace_id uuid NOT NULL, event_id uuid NOT NULL, owner_id uuid NOT NULL,
        action varchar(40) NOT NULL CHECK(action IN ('collaboration.identity','collaboration.peer.add','collaboration.peer.revoke',
          'collaboration.read','collaboration.receive','collaboration.attempt','collaboration.delivered','collaboration.retry')),
        outcome varchar(8) NOT NULL CHECK(outcome IN ('allowed','denied')), resource_id uuid,
        occurred_at timestamptz NOT NULL CHECK(isfinite(occurred_at)), PRIMARY KEY(workspace_id,event_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
      );
      GRANT SELECT,INSERT ON class_os.collaboration_identity,class_os.collaboration_peer,
        class_os.collaboration_message,class_os.collaboration_summary,class_os.collaboration_audit TO class_os_runtime;
      GRANT UPDATE(status,version) ON class_os.collaboration_peer TO class_os_runtime;
      GRANT UPDATE(attempts,next_attempt_at,delivered_at,last_error) ON class_os.collaboration_message TO class_os_runtime;
      ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
      ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_command_type_check CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire','conversation.import.admit',
        'conversation.create','conversation.rename','conversation.archive','conversation.enqueue',
        'conversation.run.claim','conversation.run.finish','conversation.run.cancel','conversation.run.reconcile','conversation.run.finish-result',
        'document.create','document.revise','document.archive','document.restore',
        'exam.create','score.record','seat.layout.create','seat.assign','seat.swap',
        'collaboration.request','collaboration.material.share','collaboration.summary.save'));
      ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_collaboration_risk_check
        CHECK(command_type NOT IN ('collaboration.request','collaboration.material.share','collaboration.summary.save') OR risk='W2');
      ALTER TABLE class_os.workspace_chat_turn DROP CONSTRAINT workspace_chat_candidate_command_check;
      ALTER TABLE class_os.workspace_chat_turn ADD CONSTRAINT workspace_chat_candidate_command_check
        CHECK(candidate IS NULL OR (jsonb_typeof(candidate)='object' AND octet_length(candidate::text)<=440000
          AND candidate->>'command' IN ('class.create','class.update','term.update','student.create','student.update_name',
          'record.create','task.create','task.update','task.complete','task.cancel','document.create','document.revise',
          'exam.create','score.record','seat.layout.create','seat.assign','seat.swap',
          'collaboration.request','collaboration.material.share','collaboration.summary.save')));
    """)


def downgrade():
    raise RuntimeError('Preserve bilateral messages, sources and receipts; use a verified checkpoint or forward fix')
