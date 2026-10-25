"""Fixed, isolated recovery provenance; no target admission."""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.conversation_import (
        workspace_id uuid PRIMARY KEY REFERENCES class_os.workspace(workspace_id), attempt_id uuid NOT NULL UNIQUE,
        restorer_id uuid NOT NULL, source_workspace_id uuid NOT NULL CHECK(source_workspace_id<>workspace_id),
        source_owner_id uuid NOT NULL CHECK(source_owner_id<>restorer_id), source_authority_id uuid NOT NULL,
        source_epoch integer NOT NULL CHECK(source_epoch BETWEEN 0 AND 4096),
        source_head_hash varchar(64) NOT NULL CHECK(source_head_hash ~ '^[0-9a-f]{64}$'),
        source_fence_hash varchar(64) NOT NULL CHECK(source_fence_hash ~ '^[0-9a-f]{64}$'), source_receipt_id uuid NOT NULL,
        source_root_binding varchar(64) NOT NULL CHECK(source_root_binding ~ '^[0-9a-f]{64}$'),
        package_hash varchar(64) NOT NULL CHECK(package_hash ~ '^[0-9a-f]{64}$'),
        target_binding varchar(64) NOT NULL CHECK(target_binding ~ '^[0-9a-f]{64}$' AND target_binding<>source_root_binding),
        source_sealed_at timestamptz NOT NULL, imported_at timestamptz NOT NULL CHECK(imported_at>=source_sealed_at),
        phase varchar(16) NOT NULL CHECK(phase='pending'), UNIQUE(workspace_id,attempt_id),
        FOREIGN KEY(workspace_id,restorer_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE TABLE class_os.conversation_provenance (
        workspace_id uuid NOT NULL, attempt_id uuid NOT NULL,
        entity_kind varchar(32) NOT NULL CHECK(entity_kind IN ('academic_term','school_class','student','enrollment',
            'student_identifier','record_revision','manual_task','conversation_thread','conversation_turn','conversation_message','conversation_run')),
        thread_id uuid, resource_id uuid NOT NULL, source_version integer NOT NULL CHECK(source_version BETWEEN 0 AND 2147483647),
        source_hash varchar(64) NOT NULL CHECK(source_hash ~ '^[0-9a-f]{64}$'),
        UNIQUE NULLS NOT DISTINCT(workspace_id,entity_kind,thread_id,resource_id,source_version),
        CHECK((entity_kind IN ('conversation_turn','conversation_message','conversation_run'))=(thread_id IS NOT NULL)),
        FOREIGN KEY(workspace_id,attempt_id) REFERENCES class_os.conversation_import(workspace_id,attempt_id)
    );
    CREATE TABLE class_os.conversation_source_audit (
        workspace_id uuid NOT NULL, attempt_id uuid NOT NULL, source_workspace_id uuid NOT NULL,
        event_id uuid NOT NULL, actor_id uuid NOT NULL, purpose varchar(32) NOT NULL, action varchar(32) NOT NULL,
        outcome varchar(16) NOT NULL CHECK(outcome IN ('allowed','denied')), occurred_at timestamptz NOT NULL,
        proposal_id uuid, payload_hash varchar(64) CHECK(payload_hash ~ '^[0-9a-f]{64}$'), receipt_id uuid, resource_id uuid,
        resource_version integer CHECK(resource_version>0), class_id uuid, term_id uuid,
        PRIMARY KEY(workspace_id,attempt_id,event_id),
        FOREIGN KEY(workspace_id,attempt_id) REFERENCES class_os.conversation_import(workspace_id,attempt_id)
    );
    REVOKE ALL ON class_os.conversation_import,class_os.conversation_provenance,class_os.conversation_source_audit FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.conversation_import,class_os.conversation_provenance,class_os.conversation_source_audit TO class_os_runtime;
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_d1_risk_check;
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_d1_risk_check CHECK(
        (command_type IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal','conversation.import.stage') AND risk='X') OR
        (command_type NOT IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal','conversation.import.stage') AND risk IN ('W1','W2')));
    ALTER TABLE class_os.business_audit DROP CONSTRAINT business_audit_action_check;
    ALTER TABLE class_os.business_audit ADD CHECK(action IN (
        'command.preview','command.approve','command.reject','command.commit','command.status','roster.list','class.context',
        'class.history','identifier.list','duplicate.list','activity.today','student.timeline',
        'agent.run.started','agent.run.completed','agent.run.failed','agent.run.cancelled','exit.summary','exit.download','audit.list',
        'model.config.read','model.test.started','model.test.completed','model.test.failed','model.enable','model.disable','model.invoke',
        'conversation.history','exit.conversation.summary','exit.conversation.download','conversation.transfer.proof'));
    ALTER TABLE class_os.export_job DROP CONSTRAINT export_job_bundle_check;
    ALTER TABLE class_os.export_job ADD CHECK(bundle->>'schema_version' IN (
        'class-os.synthetic-core-exit.v1','classmatter.synthetic-exit.v2','classmatter.synthetic-exit.v3','classmatter.synthetic-exit.v4')
        AND octet_length(bundle::text)<=2097152);
    """)


def downgrade():
    raise RuntimeError("Preserve both recovery fences; disable profile or forward-fix")
