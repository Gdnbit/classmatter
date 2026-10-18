"""Single owner ISB; credentials never share business table privileges."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE class_os.workspace (
        workspace_id uuid PRIMARY KEY,
        singleton boolean NOT NULL DEFAULT true UNIQUE CHECK(singleton=true),
        data_mode varchar(32) NOT NULL DEFAULT 'synthetic-only' CHECK(data_mode='synthetic-only'),
        created_at timestamptz NOT NULL
    );
    CREATE TABLE class_os.owner_account (
        owner_id uuid PRIMARY KEY,
        singleton boolean NOT NULL DEFAULT true UNIQUE CHECK(singleton=true),
        workspace_id uuid NOT NULL UNIQUE REFERENCES class_os.workspace(workspace_id),
        password_hash varchar(512) NOT NULL,
        credential_version integer NOT NULL CHECK(credential_version>0)
    );
    CREATE TABLE class_os.bootstrap_capability (
        singleton boolean PRIMARY KEY CHECK(singleton=true),
        secret_hash varchar(512) NOT NULL,
        expires_at timestamptz NOT NULL,
        consumed_at timestamptz
    );
    CREATE TABLE class_os.auth_session (
        token_digest char(64) PRIMARY KEY,
        owner_id uuid NOT NULL REFERENCES class_os.owner_account(owner_id),
        client_digest char(64) NOT NULL,
        csrf_digest char(64) NOT NULL,
        credential_version integer NOT NULL CHECK(credential_version>0),
        purpose varchar(16) NOT NULL CHECK(purpose IN ('business','recovery')),
        expires_at timestamptz NOT NULL,
        last_seen_at timestamptz NOT NULL,
        reauthenticated_at timestamptz NOT NULL,
        revoked_at timestamptz
    );
    CREATE TABLE class_os.recovery_code (
        code_id uuid PRIMARY KEY,
        owner_id uuid NOT NULL REFERENCES class_os.owner_account(owner_id),
        code_hash varchar(512) NOT NULL,
        credential_version integer NOT NULL CHECK(credential_version>0),
        consumed_at timestamptz
    );
    CREATE TABLE class_os.identity_rate_limit (
        action varchar(32) PRIMARY KEY CHECK(action IN ('bootstrap','login','reauthenticate','recovery_exchange','recovery_complete')),
        attempts integer NOT NULL CHECK(attempts BETWEEN 1 AND 6),
        window_start timestamptz NOT NULL
    );
    CREATE TABLE class_os.identity_audit (
        event_id uuid PRIMARY KEY,
        action varchar(32) NOT NULL CHECK(action IN ('bootstrap_arm','bootstrap','login','session','logout','reauthenticate','recovery_exchange','recovery_complete')),
        outcome varchar(16) NOT NULL CHECK(outcome IN ('allowed','denied')),
        occurred_at timestamptz NOT NULL
    );
    GRANT USAGE ON SCHEMA class_os TO class_os_identity;
    GRANT SELECT ON class_os.database_state TO class_os_identity;
    GRANT SELECT, INSERT ON class_os.workspace TO class_os_identity;
    GRANT SELECT, INSERT, UPDATE ON class_os.owner_account, class_os.bootstrap_capability, class_os.auth_session, class_os.identity_rate_limit TO class_os_identity;
    GRANT SELECT, INSERT, UPDATE, DELETE ON class_os.recovery_code TO class_os_identity;
    GRANT INSERT ON class_os.identity_audit TO class_os_identity;
    GRANT SELECT ON class_os.workspace TO class_os_runtime;
    """)


def downgrade():
    raise RuntimeError("Restore a verified snapshot or forward-fix; no destructive downgrade")
