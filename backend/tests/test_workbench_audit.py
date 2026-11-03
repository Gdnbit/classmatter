"""Explicit audit partitions do not ignore unknown or malformed new actions."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from class_os.domain.exit_package import AUDIT_COLUMNS
from class_os.domain.workbench_audit import partition_audit


WORKSPACE, OWNER = str(uuid4()), str(uuid4())
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def row(action='document.read'):
    return {**dict.fromkeys(AUDIT_COLUMNS), 'workspace_id': WORKSPACE, 'actor_id': OWNER,
            'event_id': str(uuid4()), 'action': action, 'purpose': 'manage-class', 'outcome': 'allowed',
            'occurred_at': NOW.isoformat(), 'class_id': str(uuid4()), 'term_id': str(uuid4()), 'resource_id': str(uuid4())}


def test_partition_preserves_original_rows_and_shared_bcg_commands_without_rewriting():
    documents = [row(action) for action in ('document.read', 'document.list', 'document.history')]
    command = row('command.commit')
    original = [command, *documents]
    legacy, separate = partition_audit(original, WORKSPACE, OWNER, NOW)
    assert legacy == [command] and separate == documents
    assert legacy[0] is command and separate[0] is documents[0]
    assert original == [command, *documents]


@pytest.mark.parametrize('field,value', [
    ('workspace_id', str(uuid4())), ('actor_id', str(uuid4())), ('action', 'document.delete'),
    ('purpose', 'manage-conversation'), ('outcome', 'guaranteed'), ('resource_version', 1),
    ('payload_hash', 'a' * 64), ('proposal_id', str(uuid4())), ('receipt_id', str(uuid4())),
    ('occurred_at', (NOW + timedelta(seconds=1)).isoformat()), ('class_id', None), ('term_id', None),
])
def test_malformed_document_audit_is_rejected(field, value):
    with pytest.raises(ValueError):
        partition_audit([{**row(), field: value}], WORKSPACE, OWNER, NOW)


def test_global_duplicates_extra_fields_and_unknown_legacy_actions_fail_closed():
    document = row()
    for rows in ([document, {**row('command.commit'), 'event_id': document['event_id']}],
                 [{**document, 'body': 'unexpected'}], [row('unknown.action')]):
        with pytest.raises(ValueError):
            partition_audit(rows, WORKSPACE, OWNER, NOW)


def test_unregistered_query_subclass_cannot_mint_result_capture():
    from class_os.application.workbench import WorkbenchQueryGateway
    from class_os.application.result_capture import ResultCapture
    from class_os.application.roster import CommandRejected
    from test_result_capture import setup
    capture, _, credentials, query, _ = setup()
    class UnregisteredQuery(WorkbenchQueryGateway):
        pass
    with pytest.raises(CommandRejected):
        ResultCapture(capture.ticket, credentials, UnregisteredQuery(query.identity, query.store))
