"""Minimal logout delivery receipts in the existing identity-only audit."""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.identity_audit ADD COLUMN request_id uuid,
        ADD COLUMN session_digest char(64), ADD COLUMN client_digest char(64), ADD COLUMN csrf_digest char(64);
    ALTER TABLE class_os.identity_audit ADD CHECK(
        (request_id IS NULL AND session_digest IS NULL AND client_digest IS NULL AND csrf_digest IS NULL)
        OR (request_id IS NOT NULL AND action='logout' AND outcome='allowed'
            AND session_digest IS NOT NULL AND session_digest ~ '^[0-9a-f]{64}$'
            AND client_digest IS NOT NULL AND client_digest ~ '^[0-9a-f]{64}$'
            AND csrf_digest IS NOT NULL AND csrf_digest ~ '^[0-9a-f]{64}$'));
    CREATE UNIQUE INDEX identity_logout_request ON class_os.identity_audit(request_id) WHERE request_id IS NOT NULL;
    GRANT SELECT(event_id,action,outcome,occurred_at,request_id,session_digest,client_digest,csrf_digest)
        ON class_os.identity_audit TO class_os_identity;
    ALTER TABLE class_os.identity_audit DROP CONSTRAINT identity_audit_action_check;
    ALTER TABLE class_os.identity_audit ADD CHECK(action IN (
        'bootstrap_arm','bootstrap','login','session','logout','logout_status','reauthenticate',
        'recovery_exchange','recovery_complete','logout_all','recovery_reissue'));
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
