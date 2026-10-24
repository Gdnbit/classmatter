"""Opt-in D1 source fence; no target import or automatic admission."""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.conversation_control ADD COLUMN transfer_id uuid;
    ALTER TABLE class_os.conversation_control ADD COLUMN transfer_hash varchar(64);
    ALTER TABLE class_os.conversation_control ADD COLUMN transfer_at timestamptz;
    ALTER TABLE class_os.conversation_control ADD CONSTRAINT source_transfer_tuple CHECK(
        (transfer_id IS NULL AND transfer_hash IS NULL AND transfer_at IS NULL) OR
        (transfer_id IS NOT NULL AND transfer_hash IS NOT NULL AND transfer_hash ~ '^[0-9a-f]{64}$'
         AND transfer_at IS NOT NULL AND transfer_at>=created_at AND transfer_at<=updated_at));
    GRANT UPDATE(transfer_id,transfer_hash,transfer_at) ON class_os.conversation_control TO class_os_runtime;
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_command_type_check;
    ALTER TABLE class_os.command_proposal ADD CHECK(command_type IN (
        'class.create','class.update','class.archive','term.update','student.create','student.update_identifier','student.deactivate',
        'student.update_name','record.create','record.correct','record.supersede',
        'task.create','task.update','task.complete','task.cancel','exit_export.create',
        'model_configuration.save','model_configuration.clear','conversation.control.initialize','conversation.clear',
        'conversation_exit.create','conversation.transfer.seal'));
    ALTER TABLE class_os.command_proposal DROP CONSTRAINT command_proposal_d1_risk_check;
    ALTER TABLE class_os.command_proposal ADD CONSTRAINT command_proposal_d1_risk_check CHECK(
        (command_type IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal') AND risk='X') OR
        (command_type NOT IN ('conversation.control.initialize','conversation.clear','conversation_exit.create','conversation.transfer.seal') AND risk IN ('W1','W2')));
    ALTER TABLE class_os.export_job DROP CONSTRAINT export_job_bundle_check;
    ALTER TABLE class_os.export_job ADD CHECK(
        bundle->>'schema_version' IN ('class-os.synthetic-core-exit.v1','classmatter.synthetic-exit.v2','classmatter.synthetic-exit.v3')
        AND octet_length(bundle::text)<=2097152);
    """)


def downgrade():
    raise RuntimeError("Preserve source fence; disable profile or forward-fix, no destructive downgrade")
