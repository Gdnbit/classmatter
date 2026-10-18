"""ISB metadata actions only; no business-role permission expansion."""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE class_os.identity_rate_limit DROP CONSTRAINT identity_rate_limit_action_check;
    ALTER TABLE class_os.identity_rate_limit ADD CHECK(action IN (
        'bootstrap','login','reauthenticate','recovery_exchange','recovery_complete','logout_all','recovery_reissue'));
    ALTER TABLE class_os.identity_audit DROP CONSTRAINT identity_audit_action_check;
    ALTER TABLE class_os.identity_audit ADD CHECK(action IN (
        'bootstrap_arm','bootstrap','login','session','logout','reauthenticate','recovery_exchange','recovery_complete','logout_all','recovery_reissue'));
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
