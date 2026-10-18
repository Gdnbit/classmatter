CREATE SCHEMA IF NOT EXISTS class_os_gate;

CREATE TABLE IF NOT EXISTS class_os_gate.scope_setup_consumption (
    deployment_id text NOT NULL,
    setup_artifact_id text NOT NULL,
    setup_payload_sha256 character(64) NOT NULL,
    request_sha256 character(64) NOT NULL,
    registry_generation bigint NOT NULL CHECK (registry_generation > 0),
    registry_sha256 character(64) NOT NULL,
    workspace_id text NOT NULL,
    owner_ids jsonb NOT NULL,
    consumed_at timestamp with time zone NOT NULL,
    PRIMARY KEY (deployment_id, setup_artifact_id)
);

CREATE TABLE IF NOT EXISTS class_os_gate.scope_allocation (
    deployment_id text NOT NULL,
    setup_artifact_id text NOT NULL,
    workspace_id text NOT NULL,
    owner_ids jsonb NOT NULL,
    reserved_class_id text NOT NULL UNIQUE,
    reserved_term_id text NOT NULL UNIQUE,
    allocated_at timestamp with time zone NOT NULL,
    PRIMARY KEY (deployment_id, setup_artifact_id),
    UNIQUE (deployment_id, workspace_id),
    FOREIGN KEY (deployment_id, setup_artifact_id)
        REFERENCES class_os_gate.scope_setup_consumption (deployment_id, setup_artifact_id)
);

CREATE SEQUENCE IF NOT EXISTS class_os_gate.scope_allocation_ledger_sequence;

CREATE TABLE IF NOT EXISTS class_os_gate.scope_allocation_ledger (
    ledger_sequence bigint NOT NULL PRIMARY KEY,
    deployment_id text NOT NULL,
    setup_artifact_id text NOT NULL,
    entry jsonb NOT NULL,
    entry_sha256 character(64) NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    UNIQUE (deployment_id, setup_artifact_id),
    UNIQUE (deployment_id, setup_artifact_id, ledger_sequence),
    FOREIGN KEY (deployment_id, setup_artifact_id)
        REFERENCES class_os_gate.scope_setup_consumption (deployment_id, setup_artifact_id)
);

CREATE TABLE IF NOT EXISTS class_os_gate.scope_allocation_audit (
    deployment_id text NOT NULL,
    setup_artifact_id text NOT NULL,
    ledger_sequence bigint NOT NULL,
    event_type text NOT NULL CHECK (event_type = 'scope-allocated'),
    request_sha256 character(64) NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    PRIMARY KEY (deployment_id, setup_artifact_id),
    FOREIGN KEY (deployment_id, setup_artifact_id, ledger_sequence)
        REFERENCES class_os_gate.scope_allocation_ledger
            (deployment_id, setup_artifact_id, ledger_sequence)
);

CREATE TABLE IF NOT EXISTS class_os_gate.scope_receipt_payload (
    deployment_id text NOT NULL,
    setup_artifact_id text NOT NULL,
    ledger_sequence bigint NOT NULL,
    payload jsonb NOT NULL,
    payload_sha256 character(64) NOT NULL,
    committed_at timestamp with time zone NOT NULL,
    PRIMARY KEY (deployment_id, setup_artifact_id),
    FOREIGN KEY (deployment_id, setup_artifact_id, ledger_sequence)
        REFERENCES class_os_gate.scope_allocation_ledger
            (deployment_id, setup_artifact_id, ledger_sequence)
);

CREATE OR REPLACE FUNCTION class_os_gate.reject_scope_allocation_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'scope allocation transaction rows are immutable';
END;
$$;

DROP TRIGGER IF EXISTS scope_setup_consumption_immutable ON class_os_gate.scope_setup_consumption;
CREATE TRIGGER scope_setup_consumption_immutable
BEFORE UPDATE OR DELETE ON class_os_gate.scope_setup_consumption
FOR EACH ROW EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();
DROP TRIGGER IF EXISTS scope_setup_consumption_no_truncate ON class_os_gate.scope_setup_consumption;
CREATE TRIGGER scope_setup_consumption_no_truncate
BEFORE TRUNCATE ON class_os_gate.scope_setup_consumption
FOR EACH STATEMENT EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();

DROP TRIGGER IF EXISTS scope_allocation_immutable ON class_os_gate.scope_allocation;
CREATE TRIGGER scope_allocation_immutable
BEFORE UPDATE OR DELETE ON class_os_gate.scope_allocation
FOR EACH ROW EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();
DROP TRIGGER IF EXISTS scope_allocation_no_truncate ON class_os_gate.scope_allocation;
CREATE TRIGGER scope_allocation_no_truncate
BEFORE TRUNCATE ON class_os_gate.scope_allocation
FOR EACH STATEMENT EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();

DROP TRIGGER IF EXISTS scope_allocation_ledger_immutable ON class_os_gate.scope_allocation_ledger;
CREATE TRIGGER scope_allocation_ledger_immutable
BEFORE UPDATE OR DELETE ON class_os_gate.scope_allocation_ledger
FOR EACH ROW EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();
DROP TRIGGER IF EXISTS scope_allocation_ledger_no_truncate ON class_os_gate.scope_allocation_ledger;
CREATE TRIGGER scope_allocation_ledger_no_truncate
BEFORE TRUNCATE ON class_os_gate.scope_allocation_ledger
FOR EACH STATEMENT EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();

DROP TRIGGER IF EXISTS scope_allocation_audit_immutable ON class_os_gate.scope_allocation_audit;
CREATE TRIGGER scope_allocation_audit_immutable
BEFORE UPDATE OR DELETE ON class_os_gate.scope_allocation_audit
FOR EACH ROW EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();
DROP TRIGGER IF EXISTS scope_allocation_audit_no_truncate ON class_os_gate.scope_allocation_audit;
CREATE TRIGGER scope_allocation_audit_no_truncate
BEFORE TRUNCATE ON class_os_gate.scope_allocation_audit
FOR EACH STATEMENT EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();

DROP TRIGGER IF EXISTS scope_receipt_payload_immutable ON class_os_gate.scope_receipt_payload;
CREATE TRIGGER scope_receipt_payload_immutable
BEFORE UPDATE OR DELETE ON class_os_gate.scope_receipt_payload
FOR EACH ROW EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();
DROP TRIGGER IF EXISTS scope_receipt_payload_no_truncate ON class_os_gate.scope_receipt_payload;
CREATE TRIGGER scope_receipt_payload_no_truncate
BEFORE TRUNCATE ON class_os_gate.scope_receipt_payload
FOR EACH STATEMENT EXECUTE FUNCTION class_os_gate.reject_scope_allocation_mutation();
