"""Fixed historical result rows. Activated only with complete lifecycle support."""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.conversation_message ADD CONSTRAINT conversation_message_result_target
        UNIQUE(workspace_id,thread_id,turn_id,message_id,role);
    CREATE TABLE class_os.conversation_result_receipt (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL, message_id uuid NOT NULL,
        message_role varchar(16) NOT NULL DEFAULT 'assistant' CHECK(message_role='assistant'),
        protocol varchar(16) NOT NULL CHECK(protocol IN ('legacy-plain','fixed-result')),
        text_hash varchar(64) NOT NULL CHECK(text_hash ~ '^[0-9a-f]{64}$'),
        result_hash varchar(64) NOT NULL CHECK(result_hash ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        recorded_at timestamptz NOT NULL CHECK(isfinite(recorded_at) AND recorded_at>=created_at),
        PRIMARY KEY(workspace_id,message_id), UNIQUE(workspace_id,thread_id,turn_id),
        FOREIGN KEY(workspace_id,thread_id,turn_id,message_id,message_role)
            REFERENCES class_os.conversation_message(workspace_id,thread_id,turn_id,message_id,role)
    );
    CREATE TABLE class_os.conversation_query_source (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL, message_id uuid NOT NULL,
        message_role varchar(16) NOT NULL DEFAULT 'assistant' CHECK(message_role='assistant'),
        source_id uuid NOT NULL, ordinal smallint NOT NULL CHECK(ordinal BETWEEN 1 AND 2),
        source_workspace_id uuid NOT NULL, source_owner_id uuid NOT NULL, receipt_id uuid NOT NULL,
        projection_hash varchar(64) NOT NULL CHECK(projection_hash ~ '^[0-9a-f]{64}$'),
        as_of timestamptz NOT NULL CHECK(isfinite(as_of)),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at) AND as_of<=created_at),
        PRIMARY KEY(workspace_id,source_id),
        UNIQUE(workspace_id,thread_id,turn_id,message_id,ordinal),
        UNIQUE(workspace_id,thread_id,turn_id,message_id,source_workspace_id,receipt_id),
        FOREIGN KEY(workspace_id,thread_id,turn_id,message_id,message_role)
            REFERENCES class_os.conversation_message(workspace_id,thread_id,turn_id,message_id,role)
    );
    CREATE TABLE class_os.conversation_task_draft (
        workspace_id uuid NOT NULL, thread_id uuid NOT NULL, turn_id uuid NOT NULL, message_id uuid NOT NULL,
        message_role varchar(16) NOT NULL DEFAULT 'assistant' CHECK(message_role='assistant'),
        draft_id uuid NOT NULL, title varchar(80),
        title_hash varchar(64) NOT NULL CHECK(title_hash ~ '^[0-9a-f]{64}$'),
        visibility varchar(16) NOT NULL CHECK(visibility IN ('visible','restricted')),
        created_at timestamptz NOT NULL CHECK(isfinite(created_at)),
        PRIMARY KEY(workspace_id,draft_id), UNIQUE(workspace_id,thread_id,turn_id,message_id),
        FOREIGN KEY(workspace_id,thread_id,turn_id,message_id,message_role)
            REFERENCES class_os.conversation_message(workspace_id,thread_id,turn_id,message_id,role),
        CHECK((visibility='restricted' AND title IS NULL) OR (visibility='visible' AND title IS NOT NULL
            AND title ~ '[^[:space:]]' AND title !~ '[[:cntrl:]]'))
    );
    REVOKE ALL ON class_os.conversation_query_source,class_os.conversation_task_draft FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.conversation_query_source,class_os.conversation_task_draft TO class_os_runtime;
    GRANT UPDATE(title,visibility) ON class_os.conversation_task_draft TO class_os_runtime;
    REVOKE ALL ON class_os.conversation_result_receipt FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.conversation_result_receipt TO class_os_runtime;
    ALTER TABLE class_os.conversation_provenance DROP CONSTRAINT conversation_provenance_entity_kind_check;
    ALTER TABLE class_os.conversation_origin DROP CONSTRAINT conversation_origin_entity_kind_check;
    ALTER TABLE class_os.conversation_provenance ADD CHECK(entity_kind IN ('academic_term','school_class','student','enrollment',
        'student_identifier','record_revision','manual_task','conversation_thread','conversation_turn','conversation_message','conversation_run',
        'conversation_query_source','conversation_task_draft','conversation_result_receipt'));
    ALTER TABLE class_os.conversation_origin ADD CHECK(entity_kind IN ('academic_term','school_class','student','enrollment',
        'student_identifier','record_revision','manual_task','conversation_thread','conversation_turn','conversation_message','conversation_run',
        'conversation_query_source','conversation_task_draft','conversation_result_receipt'));
    ALTER TABLE class_os.conversation_provenance DROP CONSTRAINT conversation_provenance_check;
    ALTER TABLE class_os.conversation_origin DROP CONSTRAINT conversation_origin_check;
    ALTER TABLE class_os.conversation_provenance ADD CHECK((entity_kind IN ('conversation_turn','conversation_message','conversation_run',
        'conversation_query_source','conversation_task_draft','conversation_result_receipt'))=(thread_id IS NOT NULL));
    ALTER TABLE class_os.conversation_origin ADD CHECK((entity_kind IN ('conversation_turn','conversation_message','conversation_run',
        'conversation_query_source','conversation_task_draft','conversation_result_receipt'))=(thread_id IS NOT NULL));
    ALTER TABLE class_os.conversation_origin DROP CONSTRAINT conversation_origin_check1;
    ALTER TABLE class_os.conversation_origin ADD CHECK(
        (entity_kind IN ('conversation_message','conversation_task_draft') AND body_hash IS NOT NULL AND body_hash ~ '^[0-9a-f]{64}$') OR
        (entity_kind NOT IN ('conversation_message','conversation_task_draft') AND body_hash IS NULL));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire','conversation.import.admit',
        'conversation.create','conversation.rename','conversation.archive','conversation.enqueue',
        'conversation.run.claim','conversation.run.finish','conversation.run.cancel','conversation.run.reconcile','conversation.run.finish-result'));
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_result_risk_check
        CHECK(command_type<>'conversation.run.finish-result' OR risk='W1');
    ALTER TABLE class_os.export_job DROP CONSTRAINT export_job_bundle_check;
    ALTER TABLE class_os.export_job ADD CHECK(bundle->>'schema_version' IN (
        'class-os.synthetic-core-exit.v1','classmatter.synthetic-exit.v2','classmatter.synthetic-exit.v3',
        'classmatter.synthetic-exit.v4','classmatter.synthetic-exit.v5','classmatter.synthetic-exit.v6') AND octet_length(bundle::text)<=2097152);
    """)


def downgrade():
    raise RuntimeError("Preserve result and restriction evidence; disable profile or forward-fix")
