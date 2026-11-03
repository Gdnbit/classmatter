"""Closed post-R1 working documents, not student facts, memory or Knowledge.

This module does not register commands in the frozen R1 decoder. A later
explicit workbench composition must supply QG/BCG, storage and lifecycle checks.
"""
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from .roster import identifiers, name


MAX_BODY_CHARACTERS = 100_000
MAX_BODY_BYTES = 400_000
FORMATS = frozenset({'plain-text', 'markdown'})
COMMANDS = frozenset({'document.create', 'document.revise', 'document.archive', 'document.restore'})


def version(value):
    if type(value) is not int or not 1 <= value < 2_147_483_647:
        raise ValueError('Invalid document version')


def content(title, body, format):
    name(title)
    if type(format) is not str or format not in FORMATS:
        raise ValueError('Unsupported document format')
    if type(body) is not str or len(body) > MAX_BODY_CHARACTERS:
        raise ValueError('Document body exceeds bounds')
    # Keep user text/line endings unchanged. Reject NUL, surrogates and other
    # non-text controls, while preserving ordinary multiline working drafts.
    if any((ord(char) < 32 and char not in '\t\n\r') or 0xD800 <= ord(char) <= 0xDFFF or ord(char) == 127 for char in body):
        raise ValueError('Invalid document text')
    if len(body.encode('utf-8')) > MAX_BODY_BYTES:
        raise ValueError('Document body exceeds byte bound')


class DocumentCommand:
    operation: ClassVar[str]

    def canonical(self):
        return {'command': self.operation, **{
            key: str(value) if type(value) is UUID else value
            for key, value in self.__dict__.items()
        }}


@dataclass(frozen=True)
class CreateDocument(DocumentCommand):
    document_id: UUID
    class_id: UUID
    term_id: UUID
    title: str
    body: str
    format: str = 'plain-text'
    operation: ClassVar[str] = 'document.create'

    def __post_init__(self):
        identifiers(self.document_id, self.class_id, self.term_id)
        content(self.title, self.body, self.format)


@dataclass(frozen=True)
class ReviseDocument(DocumentCommand):
    document_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    title: str
    body: str
    format: str = 'plain-text'
    operation: ClassVar[str] = 'document.revise'

    def __post_init__(self):
        identifiers(self.document_id, self.class_id, self.term_id)
        version(self.expected_version)
        content(self.title, self.body, self.format)


@dataclass(frozen=True)
class ChangeDocumentState(DocumentCommand):
    command: str
    document_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int

    def __post_init__(self):
        identifiers(self.document_id, self.class_id, self.term_id)
        version(self.expected_version)
        if type(self.command) is not str or self.command not in ('document.archive', 'document.restore'):
            raise ValueError('Unsupported document state operation')

    @property
    def operation(self):
        return self.command

    def canonical(self):
        return {key: str(value) if type(value) is UUID else value for key, value in self.__dict__.items()}


def decode_document(payload):
    if type(payload) is not dict:
        raise ValueError('Closed document command required')
    operation = payload.get('command')
    if type(operation) is not str:
        raise ValueError('Closed document operation required')
    identity = {'document_id', 'class_id', 'term_id'}
    fields = identity | {'command'}
    if operation in ('document.create', 'document.revise'):
        fields |= {'title', 'body', 'format'}
        if operation == 'document.revise':
            fields.add('expected_version')
    elif operation in ('document.archive', 'document.restore'):
        fields.add('expected_version')
    else:
        raise ValueError('Unregistered document command')
    if set(payload) != fields:
        raise ValueError('Unexpected document fields')
    values = {key: value for key, value in payload.items() if key != 'command'}
    for key in identity:
        if type(values[key]) is not str:
            raise ValueError('Canonical document identity required')
        values[key] = UUID(values[key])
    if operation == 'document.create':
        result = CreateDocument(**values)
    elif operation == 'document.revise':
        result = ReviseDocument(**values)
    else:
        result = ChangeDocumentState(operation, **values)
    if result.canonical() != payload:
        raise ValueError('Noncanonical document command')
    return result


def next_document_state(command, current):
    """Validate exact scope/version before a store may append a new revision.

    `current` is a closed persisted header projection, not client/model input.
    Gateway/store still enforce identity, active class/term and immutable history.
    """
    if type(command) not in (CreateDocument, ReviseDocument, ChangeDocumentState):
        raise ValueError('Unregistered document command')
    if type(command) is CreateDocument:
        if current is not None:
            raise ValueError('Document already exists')
        return 'draft', 1
    if (type(current) is not dict or set(current) != {'document_id', 'class_id', 'term_id', 'version', 'status'}
            or any(current[key] != getattr(command, key) for key in ('document_id', 'class_id', 'term_id'))
            or type(current['version']) is not int or current['version'] != command.expected_version
            or current['status'] not in ('draft', 'archived')):
        raise ValueError('Document version or scope conflict')
    if type(command) is ReviseDocument:
        if current['status'] != 'draft':
            raise ValueError('Archived document is read-only')
        return 'draft', command.expected_version + 1
    wanted = 'archived' if command.command == 'document.archive' else 'draft'
    if current['status'] == wanted:
        raise ValueError('Document state already applied')
    return wanted, command.expected_version + 1
