CREATE SCHEMA IF NOT EXISTS class_os_gate;

CREATE TABLE IF NOT EXISTS class_os_gate.artifact_identity_ledger (
    artifact_id text NOT NULL,
    nonce character(32) NOT NULL,
    payload_digest character(64) NOT NULL
        CONSTRAINT artifact_identity_ledger_payload_digest_format
        CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    first_observed_at timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT artifact_identity_ledger_pkey PRIMARY KEY (artifact_id),
    CONSTRAINT artifact_identity_ledger_nonce_key UNIQUE (nonce),
    CONSTRAINT artifact_identity_ledger_artifact_id_format
        CHECK (artifact_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
    CONSTRAINT artifact_identity_ledger_nonce_format
        CHECK (nonce ~ '^[0-9a-f]{32}$')
);

COMMENT ON TABLE class_os_gate.artifact_identity_ledger IS
    'Global signed-artifact identity/nonce observations; not a setup consumption ledger.';
