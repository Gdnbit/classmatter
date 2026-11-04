"""Closed native D2 data archive. Integrity is never recovery authority.

No endpoint, command registration, import, schema mutation or activation.
The live adapter must collect the complete fixed registries in one transaction.
"""
from copy import deepcopy
from types import MappingProxyType

import rfc8785

from .conversation_exit import MAX_BYTES, MAX_ROWS, _uuid, _integer, _instant
from .conversation_exit_v6 import validate_v6
from .documents import content
from .exit_package import checksum
from .workbench_audit import partition_audit


SCHEMA = 'classmatter.workbench-data.v1'
DOCUMENT_COLUMNS = MappingProxyType({
    'working_document': ('workspace_id', 'document_id', 'owner_id', 'class_id', 'term_id',
        'status', 'version', 'created_at', 'updated_at'),
    'working_document_revision': ('workspace_id', 'document_id', 'version', 'status', 'title',
        'body', 'format', 'operation', 'created_by', 'created_at'),
})
DOCUMENT_KEYS = MappingProxyType({'working_document': ('document_id',),
    'working_document_revision': ('document_id', 'version')})
FIELDS = frozenset({'schema_version', 'source_revision', 'data_mode', 'workspace_id', 'actor_id', 'created_at',
    'document_authority', 'integrity_not_authority', 'complete_exit', 'activation_allowed',
    'legacy_component', 'documents', 'document_audit', 'snapshot_hash', 'package_checksum'})


def snapshot_hash(legacy, documents):
    # Read audits change when querying a summary. Include them in the package
    # checksum, but keep the optimistic business-snapshot identity read-stable.
    return checksum({'legacy': legacy['snapshot_hash'], 'documents': documents})


def validate_documents(documents, legacy):
    if type(documents) is not dict or set(documents) != set(DOCUMENT_COLUMNS):
        raise ValueError('Invalid fixed document collections')
    workspace, actor, now = legacy['workspace_id'], legacy['actor_refs'][0], _instant(legacy['created_at'])
    classes = {(row['class_id'], row['term_id']) for row in legacy['core']['school_class']}
    heads, revisions = {}, {}
    for table, columns in DOCUMENT_COLUMNS.items():
        rows = documents[table]
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ValueError('Document collection bound exceeded')
        previous = None
        for row in rows:
            if type(row) is not dict or set(row) != set(columns) or row['workspace_id'] != workspace:
                raise ValueError('Invalid document projection or workspace')
            _uuid(row['document_id']); _integer(row['version'], 1)
            if type(row['status']) is not str or row['status'] not in ('draft', 'archived'):
                raise ValueError('Invalid document status')
            at = _instant(row['created_at'])
            if at > now:
                raise ValueError('Future document creation')
            key = tuple(row[field] for field in DOCUMENT_KEYS[table])
            if previous is not None and key <= previous:
                raise ValueError('Duplicate or unordered document identity')
            previous = key
            if table == 'working_document':
                _uuid(row['owner_id']); _uuid(row['class_id']); _uuid(row['term_id'])
                updated = _instant(row['updated_at'])
                if row['owner_id'] != actor or (row['class_id'], row['term_id']) not in classes or not at <= updated <= now:
                    raise ValueError('Invalid native document owner, scope or time')
                heads[row['document_id']] = row
            else:
                _uuid(row['created_by'])
                if row['created_by'] != actor:
                    raise ValueError('Unregistered document author')
                content(row['title'], row['body'], row['format'])
                revisions.setdefault(row['document_id'], []).append(row)
    if set(heads) != set(revisions):
        raise ValueError('Missing document head or revisions')
    for document_id, head in heads.items():
        chain = revisions[document_id]
        # Compare the bounded count before considering a possibly hostile head
        # version. Never allocate a range up to a supplied billion-row version.
        if len(chain) != head['version'] or chain[-1]['status'] != head['status']:
            raise ValueError('Incomplete document history')
        previous = None
        for number, row in enumerate(chain, 1):
            if row['version'] != number or not head['created_at'] <= row['created_at'] <= head['updated_at']:
                raise ValueError('Invalid document history sequence')
            if previous is None:
                valid = row['operation'] == 'document.create' and row['status'] == 'draft' and row['created_at'] == head['created_at']
            else:
                same = all(row[key] == previous[key] for key in ('title', 'body', 'format'))
                valid = row['created_at'] >= previous['created_at'] and (
                    (row['operation'] == 'document.revise' and row['status'] == previous['status'] == 'draft')
                    or (row['operation'] == 'document.archive' and previous['status'] == 'draft' and row['status'] == 'archived' and same)
                    or (row['operation'] == 'document.restore' and previous['status'] == 'archived' and row['status'] == 'draft' and same))
            if not valid:
                raise ValueError('Invalid document history transition')
            previous = row
        if chain[-1]['created_at'] != head['updated_at']:
            raise ValueError('Invalid current document version time')
    return {table: len(rows) for table, rows in documents.items()}


def validate_package(bundle):
    try:
        if (type(bundle) is not dict or set(bundle) != FIELDS or bundle['schema_version'] != SCHEMA
                or bundle['source_revision'] != '0027' or bundle['data_mode'] != 'synthetic-only'
                or bundle['document_authority'] != 'working-draft'
                or bundle['integrity_not_authority'] is not True or bundle['complete_exit'] is not False
                or bundle['activation_allowed'] is not False or len(rfc8785.dumps(bundle)) > MAX_BYTES):
            raise ValueError()
        legacy = bundle['legacy_component']
        counts = validate_v6(legacy)
        if (bundle['workspace_id'] != legacy['workspace_id'] or bundle['actor_id'] != legacy['actor_refs'][0]
                or bundle['created_at'] != legacy['created_at'] or any(legacy['recovery'].values())):
            raise ValueError()
        _uuid(bundle['workspace_id']); _uuid(bundle['actor_id'])
        counts.update(validate_documents(bundle['documents'], legacy))
        audits = bundle['document_audit']
        if type(audits) is not list or len(audits) > MAX_ROWS:
            raise ValueError()
        retained, document_audit = partition_audit(legacy['audit_refs'] + audits,
            bundle['workspace_id'], bundle['actor_id'], _instant(bundle['created_at']))
        if retained != legacy['audit_refs'] or document_audit != audits:
            raise ValueError()
        if (bundle['snapshot_hash'] != snapshot_hash(legacy, bundle['documents'])
                or bundle['package_checksum'] != checksum({key: value for key, value in bundle.items() if key != 'package_checksum'})):
            raise ValueError()
        return {**counts, 'document_read_audit': len(audits)}
    except Exception:
        raise ValueError('Invalid native workbench data archive; no recovery or activation authority') from None


def build_package(legacy, documents, document_audit):
    legacy, documents, document_audit = deepcopy((legacy, documents, document_audit))
    bundle = {'schema_version': SCHEMA, 'source_revision': '0027', 'data_mode': 'synthetic-only',
        'workspace_id': legacy['workspace_id'], 'actor_id': legacy['actor_refs'][0], 'created_at': legacy['created_at'],
        'document_authority': 'working-draft', 'integrity_not_authority': True, 'complete_exit': False,
        'activation_allowed': False, 'legacy_component': legacy, 'documents': documents, 'document_audit': document_audit,
        'snapshot_hash': snapshot_hash(legacy, documents)}
    bundle['package_checksum'] = checksum(bundle)
    validate_package(bundle)
    return bundle
