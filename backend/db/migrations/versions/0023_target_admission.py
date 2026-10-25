"""Fixed append-only target admission and origin digests, no body copies."""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.conversation_admission (
        workspace_id uuid PRIMARY KEY, attempt_id uuid NOT NULL, owner_id uuid NOT NULL, authority_id uuid NOT NULL,
        target_binding varchar(64) NOT NULL CHECK(target_binding ~ '^[0-9a-f]{64}$'),
        retirement_hash varchar(64) NOT NULL CHECK(retirement_hash ~ '^[0-9a-f]{64}$'), retirement_receipt_id uuid NOT NULL,
        stage_hash varchar(64) NOT NULL CHECK(stage_hash ~ '^[0-9a-f]{64}$'), stage_receipt_id uuid NOT NULL,
        target_fence_hash varchar(64) NOT NULL CHECK(target_fence_hash ~ '^[0-9a-f]{64}$'),
        origins_hash varchar(64) NOT NULL CHECK(origins_hash ~ '^[0-9a-f]{64}$'),
        batch_hash varchar(64) NOT NULL CHECK(batch_hash ~ '^[0-9a-f]{64}$'),
        source_audit_hash varchar(64) NOT NULL CHECK(source_audit_hash ~ '^[0-9a-f]{64}$'),
        origin_count integer NOT NULL CHECK(origin_count BETWEEN 0 AND 10000), created_at timestamptz NOT NULL,
        receipt_id uuid NOT NULL, proof_hash varchar(64) NOT NULL CHECK(proof_hash ~ '^[0-9a-f]{64}$'),
        UNIQUE(workspace_id,attempt_id),
        FOREIGN KEY(workspace_id,attempt_id) REFERENCES class_os.conversation_import(workspace_id,attempt_id),
        FOREIGN KEY(workspace_id,owner_id) REFERENCES class_os.owner_account(workspace_id,owner_id)
    );
    CREATE TABLE class_os.conversation_origin (
        workspace_id uuid NOT NULL, attempt_id uuid NOT NULL,
        entity_kind varchar(32) NOT NULL CHECK(entity_kind IN ('academic_term','school_class','student','enrollment',
            'student_identifier','record_revision','manual_task','conversation_thread','conversation_turn','conversation_message','conversation_run')),
        thread_id uuid, resource_id uuid NOT NULL, source_version integer NOT NULL CHECK(source_version BETWEEN 0 AND 2147483647),
        source_hash varchar(64) NOT NULL CHECK(source_hash ~ '^[0-9a-f]{64}$'),
        identity_hash varchar(64) NOT NULL CHECK(identity_hash ~ '^[0-9a-f]{64}$'),
        body_hash varchar(64), source_open boolean NOT NULL, initial_state varchar(16),
        UNIQUE NULLS NOT DISTINCT(workspace_id,entity_kind,thread_id,resource_id,source_version),
        CHECK((entity_kind IN ('conversation_turn','conversation_message','conversation_run'))=(thread_id IS NOT NULL)),
        CHECK((entity_kind='conversation_message' AND body_hash IS NOT NULL AND body_hash ~ '^[0-9a-f]{64}$') OR
              (entity_kind<>'conversation_message' AND body_hash IS NULL)),
        CHECK(NOT source_open OR entity_kind='student_identifier'),
        CHECK((entity_kind IN ('academic_term','school_class','student','enrollment','manual_task','conversation_thread')
                AND initial_state IS NOT NULL AND CASE
                    WHEN entity_kind IN ('academic_term','school_class') THEN initial_state IN ('active','archived')
                    WHEN entity_kind IN ('student','enrollment') THEN initial_state IN ('active','inactive')
                    WHEN entity_kind='manual_task' THEN initial_state IN ('not-started','in-progress','waiting','done','cancelled')
                    ELSE initial_state IN ('active','archived','cleared') END)
              OR (entity_kind NOT IN ('academic_term','school_class','student','enrollment','manual_task','conversation_thread') AND initial_state IS NULL)),
        FOREIGN KEY(workspace_id,attempt_id) REFERENCES class_os.conversation_admission(workspace_id,attempt_id)
    );
    REVOKE ALL ON class_os.conversation_admission,class_os.conversation_origin FROM PUBLIC;
    GRANT SELECT,INSERT ON class_os.conversation_admission,class_os.conversation_origin TO class_os_runtime;
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede','task.create','task.update','task.complete','task.cancel',
        'exit_export.create','model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal','conversation.import.stage','conversation.transfer.retire','conversation.import.admit'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_d1_risk_check;
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_d1_risk_check CHECK(
        (command_type IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal',
                         'conversation.import.stage','conversation.transfer.retire','conversation.import.admit') AND risk='X') OR
        (command_type NOT IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal',
                             'conversation.import.stage','conversation.transfer.retire','conversation.import.admit') AND risk IN ('W1','W2')));
    ALTER TABLE class_os.export_job DROP CONSTRAINT export_job_bundle_check;
    ALTER TABLE class_os.export_job ADD CHECK(bundle->>'schema_version' IN (
        'class-os.synthetic-core-exit.v1','classmatter.synthetic-exit.v2','classmatter.synthetic-exit.v3',
        'classmatter.synthetic-exit.v4','classmatter.synthetic-exit.v5') AND octet_length(bundle::text)<=2097152);
    """)


def downgrade():
    raise RuntimeError("Preserve admission and restriction evidence; disable profile or forward-fix")
