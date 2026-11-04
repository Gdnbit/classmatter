"""Closed archive validation, including rehashed structural tampering."""
from copy import deepcopy
from uuid import uuid4

import pytest

from class_os.domain.workbench_export import (build_package, validate_package, snapshot_hash,
    DOCUMENT_COLUMNS, DOCUMENT_KEYS, MAX_BYTES)
from class_os.domain.exit_package import checksum, AUDIT_COLUMNS
from class_os.domain.conversation_exit_v6 import validate_v6
from test_conversation_exit_v6 import sample as legacy_sample


def sample():
    legacy = legacy_sample('chat')
    scope = legacy['core']['school_class'][0]
    workspace, actor, at = legacy['workspace_id'], legacy['actor_refs'][0], legacy['created_at']
    document = str(uuid4())
    head = dict(workspace_id=workspace, document_id=document, owner_id=actor, class_id=scope['class_id'],
        term_id=scope['term_id'], status='draft', version=4, created_at=at, updated_at=at)
    revisions = []
    for version, operation, status in ((1, 'document.create', 'draft'), (2, 'document.revise', 'draft'),
                                        (3, 'document.archive', 'archived'), (4, 'document.restore', 'draft')):
        revisions.append(dict(workspace_id=workspace, document_id=document, version=version, status=status,
            title='synthetic working document', body='original text' if version == 1 else 'revised text\r\n<script>untrusted</script>',
            format='markdown', operation=operation, created_by=actor, created_at=at))
    audit = {key: None for key in AUDIT_COLUMNS}
    audit.update(workspace_id=workspace, actor_id=actor, event_id=str(uuid4()), purpose='manage-class',
        action='document.read', outcome='allowed', occurred_at=at, class_id=scope['class_id'],
        term_id=scope['term_id'], resource_id=document)
    return build_package(legacy, {'working_document': [head], 'working_document_revision': revisions}, [audit])


def rehash(value):
    value['snapshot_hash'] = snapshot_hash(value['legacy_component'], value['documents'])
    value['package_checksum'] = checksum({key: item for key, item in value.items() if key != 'package_checksum'})


def test_complete_fixed_rows_keep_all_revisions_and_never_grant_recovery_authority():
    value = sample()
    counts = validate_package(value)
    assert counts['working_document'] == 1 and counts['working_document_revision'] == 4 and counts['document_read_audit'] == 1
    assert value['documents']['working_document_revision'][0]['body'] == 'original text'
    assert '\r\n<script>' in value['documents']['working_document_revision'][3]['body']
    assert value['complete_exit'] is False and value['activation_allowed'] is False and value['integrity_not_authority'] is True
    with pytest.raises(ValueError):
        validate_v6(value)


def test_fixed_columns_match_current_d2_surface_without_generic_database_projection():
    from class_os.infrastructure.persistence.schema_inventory import D2_COLUMNS
    assert {key: frozenset(columns) for key, columns in DOCUMENT_COLUMNS.items()} == D2_COLUMNS


def test_empty_documents_are_supported_and_input_snapshots_are_not_mutated():
    legacy = legacy_sample('read')
    documents = {key: [] for key in DOCUMENT_COLUMNS}
    before = deepcopy(legacy)
    result = build_package(legacy, documents, [])
    assert validate_package(result)['working_document'] == 0 and legacy == before
    result['legacy_component']['core']['school_class'][0]['name'] = 'changed local object'
    assert legacy == before


@pytest.mark.parametrize('field,value', [('complete_exit', True), ('complete_exit', 0), ('activation_allowed', True),
    ('activation_allowed', 0), ('integrity_not_authority', 1), ('document_authority', 'domain-data'),
    ('source_revision', '9999'), ('data_mode', 'production'), ('workspace_id', str(uuid4())), ('actor_id', str(uuid4()))])
def test_rehashed_authority_scope_or_future_version_cannot_be_promoted(field, value):
    bundle = sample(); bundle[field] = value; rehash(bundle)
    with pytest.raises(ValueError):
        validate_package(bundle)


@pytest.mark.parametrize('mutation', ['head-missing', 'revision-missing', 'duplicate-head', 'duplicate-revision', 'gap',
    'huge-version', 'boolean-version', 'wrong-owner', 'wrong-class', 'wrong-term', 'wrong-workspace', 'wrong-author',
    'unknown-column', 'unknown-table', 'archived-edit', 'archive-content-change', 'restore-content-change',
    'unknown-operation', 'head-time', 'revision-time', 'invalid-time', 'nul', 'bad-format', 'extra-secret'])
def test_rehashed_missing_rows_scope_history_content_and_unknown_fields_are_rejected(mutation):
    value = sample(); documents = value['documents']; head = documents['working_document'][0]
    rows = documents['working_document_revision']
    if mutation == 'head-missing': documents['working_document'].clear()
    elif mutation == 'revision-missing': rows.pop()
    elif mutation == 'duplicate-head': documents['working_document'].append(deepcopy(head))
    elif mutation == 'duplicate-revision': rows.append(deepcopy(rows[-1]))
    elif mutation == 'gap': rows[1]['version'] = 3
    elif mutation == 'huge-version': head['version'] = 2147483647
    elif mutation == 'boolean-version': rows[0]['version'] = True
    elif mutation == 'wrong-owner': head['owner_id'] = str(uuid4())
    elif mutation == 'wrong-class': head['class_id'] = str(uuid4())
    elif mutation == 'wrong-term': head['term_id'] = str(uuid4())
    elif mutation == 'wrong-workspace': head['workspace_id'] = str(uuid4())
    elif mutation == 'wrong-author': rows[-1]['created_by'] = str(uuid4())
    elif mutation == 'unknown-column': rows[0]['inference'] = 'unverified'
    elif mutation == 'unknown-table': documents['arbitrary_fact'] = []
    elif mutation == 'archived-edit': rows[3]['operation'] = 'document.revise'
    elif mutation == 'archive-content-change': rows[2]['body'] = 'changed during archive'
    elif mutation == 'restore-content-change': rows[3]['title'] = 'changed during restore'
    elif mutation == 'unknown-operation': rows[1]['operation'] = 'arbitrary.ddl'
    elif mutation == 'head-time': head['updated_at'] = '2099-01-01T00:00:00+00:00'
    elif mutation == 'revision-time': rows[1]['created_at'] = '2000-01-01T00:00:00+00:00'
    elif mutation == 'invalid-time': rows[1]['created_at'] = 'not-an-instant'
    elif mutation == 'nul': rows[1]['body'] = '\0'
    elif mutation == 'bad-format': rows[1]['format'] = 'executable-html'
    elif mutation == 'extra-secret': value['credentials'] = {'synthetic': 'not allowed'}
    rehash(value)
    with pytest.raises(ValueError):
        validate_package(value)


@pytest.mark.parametrize('mutation', ['duplicate-event', 'wrong-purpose', 'unknown-action', 'forged-commit', 'legacy-event', 'foreign-workspace'])
def test_every_document_audit_stays_inside_closed_combined_audit_integrity(mutation):
    value = sample(); row = value['document_audit'][0]
    if mutation == 'duplicate-event': row['event_id'] = value['legacy_component']['audit_refs'][0]['event_id']
    elif mutation == 'wrong-purpose': row['purpose'] = 'exit-recovery'
    elif mutation == 'unknown-action': row['action'] = 'arbitrary.ddl'
    elif mutation == 'forged-commit': row['receipt_id'] = str(uuid4())
    elif mutation == 'legacy-event': row.update(value['legacy_component']['audit_refs'][0])
    elif mutation == 'foreign-workspace': row['workspace_id'] = str(uuid4())
    rehash(value)
    with pytest.raises(ValueError):
        validate_package(value)


def test_read_audit_changes_package_checksum_but_not_business_snapshot_identity():
    value = sample(); before = value['snapshot_hash'], value['package_checksum']
    extra = deepcopy(value['document_audit'][0]); extra['event_id'] = str(uuid4())
    value['document_audit'].append(extra); rehash(value)
    assert validate_package(value)
    assert value['snapshot_hash'] == before[0] and value['package_checksum'] != before[1]


def test_oversized_archive_is_rejected_instead_of_truncated():
    value = sample()
    for row in value['documents']['working_document_revision']:
        row['body'] = '合' * 100000
    rehash(value)
    assert sum(len(row['body'].encode('utf-8')) for row in value['documents']['working_document_revision']) > MAX_BYTES
    with pytest.raises(ValueError):
        validate_package(value)
