"""Closed D2 audit composition, never a migration or permission mechanism."""
from .conversation_exit import MAX_ROWS, _instant
from .conversation_exit_v4 import validate_audit
from .exit_package import AUDIT_COLUMNS, NULLABLE_AUDIT, _validate_column


DOCUMENT_READ_ACTIONS = frozenset({'document.list', 'document.read', 'document.history'})


def partition_audit(rows, workspace, actor, at, *, classroom=False):
    """Validate every row before using an old conversation component proof.

    Only the three new read actions form the document partition. Shared BCG
    command audits remain in the original partition, including document writes.
    This result is not a complete D2 exit package or import authority.
    """
    if type(classroom) is not bool or type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError('Invalid workbench audit size')
    read_actions = DOCUMENT_READ_ACTIONS | (frozenset({'exam.list', 'exam.read', 'seat.read'}) if classroom else frozenset())
    legacy, documents, seen = [], [], set()
    for row in rows:
        if type(row) is not dict or set(row) != set(AUDIT_COLUMNS):
            raise ValueError('Invalid workbench audit columns')
        for field in AUDIT_COLUMNS:
            _validate_column(field, row[field], nullable=field in NULLABLE_AUDIT)
        if row['event_id'] in seen:
            raise ValueError('Duplicate workbench audit identity')
        seen.add(row['event_id'])
        if row['action'] not in read_actions:
            legacy.append(row)
            continue
        if (row['workspace_id'] != workspace or row['actor_id'] != actor or row['purpose'] != 'manage-class'
                or row['outcome'] not in ('allowed', 'denied') or _instant(row['occurred_at']) > at
                or (row['outcome'] == 'allowed' and any(row[field] is None for field in ('class_id', 'term_id', 'resource_id')))
                or any(row[field] is not None for field in ('proposal_id', 'payload_hash', 'receipt_id', 'resource_version'))):
            raise ValueError('Invalid document read audit')
        documents.append(row)
    validate_audit(legacy, workspace, actor, at)  # Unknown actions stay rejected.
    return legacy, documents
