"""Closed, non-replayable identity result receipts; no secret output storage."""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.identity_audit DROP CONSTRAINT identity_audit_check;
    ALTER TABLE class_os.identity_audit ADD CHECK(
        (request_id IS NULL AND session_digest IS NULL AND client_digest IS NULL AND csrf_digest IS NULL)
        OR (request_id IS NOT NULL AND outcome='allowed'
            AND client_digest IS NOT NULL AND client_digest ~ '^[0-9a-f]{64}$'
            AND csrf_digest IS NOT NULL AND csrf_digest ~ '^[0-9a-f]{64}$'
            AND ((action IN ('bootstrap','login','recovery_exchange') AND session_digest IS NULL)
              OR (action IN ('logout','reauthenticate','logout_all','recovery_reissue','recovery_complete')
                  AND session_digest IS NOT NULL AND session_digest ~ '^[0-9a-f]{64}$'))));
    ALTER TABLE class_os.identity_audit DROP CONSTRAINT identity_audit_action_check;
    ALTER TABLE class_os.identity_audit ADD CHECK(action IN (
        'bootstrap_arm','bootstrap','login','session','logout','logout_status','operation_status','reauthenticate',
        'recovery_exchange','recovery_complete','logout_all','recovery_reissue'));
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
