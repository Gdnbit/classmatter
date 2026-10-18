CREATE TABLE task_projection (
    task_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    title text NOT NULL,
    status text NOT NULL CHECK (status IN ('OPEN', 'DONE')),
    source_ref text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE audit_projection (
    audit_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    action text NOT NULL,
    target_ref text NOT NULL,
    occurred_at timestamptz NOT NULL
);

INSERT INTO task_projection VALUES
('10000000-0000-5000-8000-000000000001', '20000000-0000-5000-8000-000000000001', '合成任务：核对回执', 'OPEN', 'fact-synthetic-001@v1', '2026-09-21T08:00:00+08:00'),
('10000000-0000-5000-8000-000000000002', '20000000-0000-5000-8000-000000000001', '合成任务：等待回复', 'DONE', 'fact-synthetic-002@v1', '2026-09-21T08:05:00+08:00');

INSERT INTO audit_projection VALUES
('30000000-0000-5000-8000-000000000001', '20000000-0000-5000-8000-000000000001', 'synthetic.seed', 'task_projection', '2026-09-21T08:10:00+08:00');
