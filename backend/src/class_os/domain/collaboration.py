"""Two-person material collection. Peer messages are attributed material, not facts.

Only fixed request/share/summary commands enter the existing human BCG. The
protocol cannot request tools, query another workspace, or confer school roles.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import ClassVar, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
import rfc8785

from .documents import DocumentCommand, content, version
from .roster import identifiers, name


MAX_MATERIAL = 12000


class ClosedValue(BaseModel):
    model_config = ConfigDict(extra='forbid')


def endpoint(value):
    # This first slice connects two owned loopback instances. Do not silently
    # turn the password-free local API into an Internet-facing server.
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('Owned loopback endpoint required')
    return f'http://127.0.0.1:{parsed.port}'


class Invitation(ClosedValue):
    kind: Literal['classmatter.collaboration-invite.v1'] = 'classmatter.collaboration-invite.v1'
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=80)
    endpoint: str = Field(max_length=128)
    public_key: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def checked(self):
        name(self.name)
        if endpoint(self.endpoint) != self.endpoint:
            raise ValueError('Noncanonical peer endpoint')
        return self

    def invitation(self):
        return json.dumps(self.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':'))


class MaterialMessage(ClosedValue):
    kind: Literal['classmatter.collaboration-material.v1'] = 'classmatter.collaboration-material.v1'
    message_id: UUID
    request_id: UUID
    sender: UUID
    receiver: UUID
    operation: Literal['request', 'material']
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=MAX_MATERIAL)
    source_document_id: UUID | None = None
    source_version: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode='after')
    def checked(self):
        name(self.title)
        content(self.title, self.body, 'markdown')
        if self.sender == self.receiver:
            raise ValueError('Distinct workspaces required')
        if self.operation == 'request':
            if self.message_id != self.request_id or self.source_document_id is not None or self.source_version is not None:
                raise ValueError('Request cannot invent material provenance')
            if len(self.body) > 1000:
                raise ValueError('Request exceeds limit')
        elif self.source_document_id is None or self.source_version is None or self.message_id == self.request_id:
            raise ValueError('Material needs its actual document version')
        return self

    def digest(self):
        return sha256(rfc8785.dumps(self.model_dump(mode='json'))).hexdigest()


@dataclass(frozen=True)
class RequestMaterial(DocumentCommand):
    request_id: UUID
    peer_id: UUID
    class_id: UUID
    term_id: UUID
    thread_id: UUID
    title: str
    body: str
    operation: ClassVar[str] = 'collaboration.request'

    def __post_init__(self):
        identifiers(self.request_id, self.peer_id, self.class_id, self.term_id, self.thread_id)
        name(self.title)
        content(self.title, self.body, 'markdown')
        if not self.body.strip() or len(self.body) > 1000:
            raise ValueError('Bounded material request required')


@dataclass(frozen=True)
class ShareMaterial(DocumentCommand):
    message_id: UUID
    request_id: UUID
    peer_id: UUID
    class_id: UUID
    term_id: UUID
    thread_id: UUID
    document_id: UUID
    expected_version: int
    title: str
    body: str
    operation: ClassVar[str] = 'collaboration.material.share'

    def __post_init__(self):
        identifiers(self.message_id, self.request_id, self.peer_id, self.class_id, self.term_id,
                    self.thread_id, self.document_id)
        version(self.expected_version)
        name(self.title)
        content(self.title, self.body, 'markdown')
        if not self.body.strip() or len(self.body) > MAX_MATERIAL:
            raise ValueError('Material exceeds supported slice')


@dataclass(frozen=True)
class SaveCollectedSummary(DocumentCommand):
    request_id: UUID
    source_message_id: UUID
    document_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    title: str
    body: str
    format: str = 'markdown'
    operation: ClassVar[str] = 'collaboration.summary.save'

    def __post_init__(self):
        identifiers(self.request_id, self.source_message_id, self.document_id, self.class_id, self.term_id)
        if type(self.expected_version) is not int or not 0 <= self.expected_version < 2147483647:
            raise ValueError('Exact summary version required')
        if self.title != '班级工作小结' or self.format != 'markdown':
            raise ValueError('Only class work summaries are supported')
        content(self.title, self.body, self.format)


COMMAND_TYPES = (RequestMaterial, ShareMaterial, SaveCollectedSummary)
COMMANDS = frozenset(cls.operation for cls in COMMAND_TYPES)


def decode_collaboration(payload):
    if type(payload) is not dict:
        raise ValueError('Closed collaboration command required')
    cls = next((value for value in COMMAND_TYPES if value.operation == payload.get('command')), None)
    if cls is None or set(payload) != {'command', *cls.__dataclass_fields__.keys()} - {'operation'}:
        raise ValueError('Unsupported collaboration command fields')
    values = {key: UUID(value) if key.endswith('_id') else value for key, value in payload.items() if key != 'command'}
    command = cls(**values)
    if command.canonical() != payload:
        raise ValueError('Noncanonical collaboration command')
    return command


def source_citation(peer_name, message):
    return f'## 同事提供的材料\n\n{peer_name}提供：《{message.title}》（第{message.source_version}版）\n\n{message.body}'
