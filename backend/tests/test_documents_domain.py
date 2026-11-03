"""Working-document invariants; no storage activation or business writes."""
from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from class_os.domain.documents import (CreateDocument, ReviseDocument, ChangeDocumentState,
    decode_document, next_document_state, MAX_BODY_CHARACTERS)
from class_os.domain.roster import decode as decode_r1


def draft():
    return CreateDocument(uuid4(), uuid4(), uuid4(), '合成班级工作小结', '教师编辑的工作草稿\r\n不自动成为学生事实。')


def header(command, *, version=1, status='draft'):
    return {key: getattr(command, key) for key in ('document_id', 'class_id', 'term_id')} | {'version': version, 'status': status}


def test_working_document_roundtrip_preserves_multiline_text_and_is_not_r1_write():
    command = draft()
    assert decode_document(command.canonical()) == command
    assert command.canonical()['body'] == command.body
    assert next_document_state(command, None) == ('draft', 1)
    with pytest.raises(ValueError):
        decode_r1(command.canonical())
    with pytest.raises(FrozenInstanceError):
        command.body = 'changed'


@pytest.mark.parametrize('changes', [
    {'title': ''}, {'title': ' leading space'}, {'title': 'x' * 81},
    {'body': '\x00'}, {'body': '\ud800'}, {'body': '\x1bterminal'},
    {'body': 'x' * (MAX_BODY_CHARACTERS + 1)}, {'body': b'not text'},
    {'format': 'html'}, {'format': 'docx'}, {'format': None},
])
def test_invalid_or_binary_document_content_cannot_become_a_command(changes):
    with pytest.raises(ValueError):
        replace(draft(), **changes)


@pytest.mark.parametrize('changes', [
    {'authority': 'verified-fact'}, {'sql': 'synthetic-unregistered'},
    {'path': 'elsewhere'}, {'command': 'document.delete'}, {'format': 'html'},
    {'class_id': None}, {'class_id': 7},
])
def test_closed_payload_rejects_arbitrary_fields_actions_and_authority(changes):
    with pytest.raises((ValueError, TypeError)):
        decode_document({**draft().canonical(), **changes})


@pytest.mark.parametrize('value', [True, False, 0, -1, 2_147_483_647, 1.0, '1'])
def test_revision_version_is_strict_and_bounded(value):
    value_command = draft()
    with pytest.raises(ValueError):
        ReviseDocument(value_command.document_id, value_command.class_id, value_command.term_id, value, '草稿', '')


def test_revision_scope_cas_and_archive_restore_are_explicit_and_monotonic():
    created = draft()
    revise = ReviseDocument(created.document_id, created.class_id, created.term_id, 1, '更新的小结', '<script>stored as text</script>', 'markdown')
    assert decode_document(revise.canonical()) == revise
    assert next_document_state(revise, header(created)) == ('draft', 2)
    for changed in ({'class_id': uuid4()}, {'term_id': uuid4()}, {'document_id': uuid4()}, {'version': 2}, {'version': True}, {'status': 'published'}):
        with pytest.raises(ValueError):
            next_document_state(revise, {**header(created), **changed})
    with pytest.raises(ValueError):
        next_document_state(revise, header(created, status='archived'))
    archive = ChangeDocumentState('document.archive', created.document_id, created.class_id, created.term_id, 2)
    assert next_document_state(archive, header(created, version=2)) == ('archived', 3)
    restore = replace(archive, command='document.restore', expected_version=3)
    assert decode_document(restore.canonical()) == restore
    assert next_document_state(restore, header(created, version=3, status='archived')) == ('draft', 4)
    with pytest.raises(ValueError):
        next_document_state(restore, header(created, version=3))
    with pytest.raises(ValueError):
        next_document_state(created, header(created))
