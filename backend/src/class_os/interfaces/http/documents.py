"""Opt-in typed document adapters. Original BCG remains the write authority."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import Field, model_validator
from starlette.responses import Response

from class_os.domain.documents import decode_document
from class_os.application.document_artifacts import OfficeRenderer, OfficeArtifact, ArtifactTooLarge, MEDIA, MAX_BYTES
from .contracts import WireModel
from .roster import ApprovalBody, ProposalBody, CommitBody, ReceiptResponse, CommandStatusResponse, credentials


class DocumentCreate(WireModel):
    command: Literal['document.create']
    document_id: UUID
    class_id: UUID
    term_id: UUID
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(max_length=100000)
    format: Literal['plain-text', 'markdown']

    @model_validator(mode='after')
    def domain_validation(self):
        decode_document(self.model_dump(mode='json'))
        return self


class DocumentRevise(DocumentCreate):
    command: Literal['document.revise']
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)


class DocumentState(WireModel):
    command: Literal['document.archive', 'document.restore']
    document_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)


DocumentCommand = Annotated[DocumentCreate | DocumentRevise | DocumentState, Field(discriminator='command')]


class DocumentPreview(WireModel):
    schema_version: Literal['classmatter.document-preview.v1'] = 'classmatter.document-preview.v1'
    proposal_id: UUID
    payload_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    risk: Literal['W2']
    expires_at: datetime
    # Standard JSON Schema union; command literals make branches disjoint.
    # The HTTP request retains its discriminated union for precise parsing.
    payload: DocumentCreate | DocumentRevise | DocumentState


class DocumentReceipt(ReceiptResponse):
    schema_version: Literal['classmatter.document-receipt.v1'] = 'classmatter.document-receipt.v1'
    version: int = Field(strict=True, ge=1, le=2147483647)


class DocumentApproval(WireModel):
    schema_version: Literal['classmatter.document-approval.v1'] = 'classmatter.document-approval.v1'
    approval: str = Field(min_length=32, max_length=128)


class DocumentRejection(WireModel):
    schema_version: Literal['classmatter.document-rejection.v1'] = 'classmatter.document-rejection.v1'
    status: Literal['rejected']


class DocumentMetadata(WireModel):
    document_id: UUID
    class_id: UUID
    term_id: UUID
    title: str = Field(min_length=1, max_length=80)
    format: Literal['plain-text', 'markdown']
    version: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['draft', 'archived']
    created_at: datetime
    updated_at: datetime


class RevisionMetadata(WireModel):
    version: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['draft', 'archived']
    title: str = Field(min_length=1, max_length=80)
    format: Literal['plain-text', 'markdown']
    operation: Literal['document.create', 'document.revise', 'document.archive', 'document.restore']
    created_by: UUID
    created_at: datetime


class DocumentRevision(RevisionMetadata):
    body: str = Field(max_length=100000)


class DocumentView(DocumentRevision):
    document_id: UUID
    class_id: UUID
    term_id: UUID
    updated_at: datetime


class DocumentResponse(WireModel):
    schema_version: Literal['classmatter.document.v1'] = 'classmatter.document.v1'
    content_authority: Literal['working-draft'] = 'working-draft'
    workspace_id: UUID
    data: DocumentView


class RevisionResponse(WireModel):
    schema_version: Literal['classmatter.document-revision.v1'] = 'classmatter.document-revision.v1'
    content_authority: Literal['working-draft'] = 'working-draft'
    document_id: UUID
    workspace_id: UUID
    class_id: UUID
    term_id: UUID
    data: DocumentRevision


class DocumentPage(WireModel):
    schema_version: Literal['classmatter.document-list.v1'] = 'classmatter.document-list.v1'
    content_authority: Literal['working-draft'] = 'working-draft'
    workspace_id: UUID
    class_id: UUID
    term_id: UUID
    data: list[DocumentMetadata] = Field(max_length=50)
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    next_offset: int | None = Field(strict=True, ge=50, lt=10000)


class RevisionPage(DocumentPage):
    schema_version: Literal['classmatter.document-history.v1'] = 'classmatter.document-history.v1'
    data: list[RevisionMetadata] = Field(max_length=50)
    document_id: UUID


Offset = Annotated[int, Path(ge=50, lt=10000, multiple_of=50)]
Snapshot = Annotated[str, Path(pattern=r'^[a-f0-9]{64}$')]
Version = Annotated[int, Path(ge=1, le=2147483647)]


def router(business, query, *, renderer: OfficeRenderer):
    routes = APIRouter(prefix='/api/workspaces/{workspace_id}')

    @routes.post('/document-commands/preview', response_model=DocumentPreview)
    def preview(workspace_id: UUID, request: Request, body: DocumentCommand):
        auth = credentials(request, workspace_id, write=True)
        try:
            command = decode_document(body.model_dump(mode='json'))
        except (TypeError, ValueError):
            raise HTTPException(400) from None
        result = business.preview(*auth, command)
        return {'proposal_id': result.proposal_id, 'payload_hash': result.payload_hash, 'risk': result.risk,
                'expires_at': result.expires_at, 'payload': result.command.canonical()}

    @routes.post('/document-commands/approve', response_model=DocumentApproval)
    def approve(workspace_id: UUID, request: Request, body: ApprovalBody):
        approval = business.approve(*credentials(request, workspace_id, write=True), body.proposal_id, body.payload_hash)
        return {'schema_version': 'classmatter.document-approval.v1', 'approval': approval}

    @routes.post('/document-commands/reject', response_model=DocumentRejection)
    def reject(workspace_id: UUID, request: Request, body: ProposalBody):
        business.reject(*credentials(request, workspace_id, write=True), body.proposal_id)
        return {'schema_version': 'classmatter.document-rejection.v1', 'status': 'rejected'}

    @routes.post('/document-commands/commit', response_model=DocumentReceipt)
    def commit(workspace_id: UUID, request: Request, body: CommitBody):
        return business.commit(*credentials(request, workspace_id, write=True), body.proposal_id, body.idempotency_key,
                               body.approval.get_secret_value() if body.approval else None)

    @routes.get('/document-commands/{proposal_id}/receipts/{key}', response_model=CommandStatusResponse)
    def status(workspace_id: UUID, proposal_id: UUID, key: UUID, request: Request):
        return query.command_status(*credentials(request, workspace_id), proposal_id, key)

    base = '/classes/{class_id}/terms/{term_id}/documents'

    @routes.get(base, response_model=DocumentPage)
    def listing(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return query.page(*credentials(request, workspace_id), class_id, term_id)

    @routes.get(base + '/pages/{snapshot}/{offset}', response_model=DocumentPage)
    def listing_page(workspace_id: UUID, class_id: UUID, term_id: UUID, snapshot: Snapshot, offset: Offset, request: Request):
        return query.page(*credentials(request, workspace_id), class_id, term_id, offset=offset, snapshot=snapshot)

    @routes.get(base + '/{document_id}', response_model=DocumentResponse)
    def document(workspace_id: UUID, class_id: UUID, term_id: UUID, document_id: UUID, request: Request):
        return {'workspace_id': workspace_id,
                'data': query.document(*credentials(request, workspace_id), class_id, term_id, document_id)}

    @routes.get(base + '/{document_id}/exports/{version}/{format}', responses={200: {'content': {
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {},
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': {}}}}, response_class=Response)
    def export(workspace_id: UUID, class_id: UUID, term_id: UUID, document_id: UUID, version: Version,
               format: Literal['docx', 'pptx'], request: Request):
        value = query.document(*credentials(request, workspace_id), class_id, term_id, document_id)
        if value['version'] != version:
            raise HTTPException(409)
        try:
            artifact = renderer(value['title'], value['body'], value['format'], format)
        except ArtifactTooLarge:
            raise HTTPException(413) from None
        if (type(artifact) is not OfficeArtifact or type(artifact.content) is not bytes or not artifact.content.startswith(b'PK')
                or not 1 <= len(artifact.content) <= MAX_BYTES or artifact.media_type != MEDIA[format]
                or type(artifact.filename) is not str or not 1 <= len(artifact.filename) <= 100
                or not artifact.filename.endswith('.' + format)
                or any(ord(char) < 32 or char in '/\\' for char in artifact.filename)):
            raise HTTPException(503)
        return Response(artifact.content, media_type=artifact.media_type, headers={
            'content-disposition': "attachment; filename*=UTF-8''" + quote(artifact.filename, safe=''),
            'x-classmatter-document-id': str(document_id), 'x-classmatter-document-version': str(version),
            'cache-control': 'no-store', 'x-content-type-options': 'nosniff'})

    @routes.get(base + '/{document_id}/history', response_model=RevisionPage)
    def history(workspace_id: UUID, class_id: UUID, term_id: UUID, document_id: UUID, request: Request):
        return query.page(*credentials(request, workspace_id), class_id, term_id, document_id=document_id)

    @routes.get(base + '/{document_id}/history/pages/{snapshot}/{offset}', response_model=RevisionPage)
    def history_page(workspace_id: UUID, class_id: UUID, term_id: UUID, document_id: UUID, snapshot: Snapshot,
                     offset: Offset, request: Request):
        return query.page(*credentials(request, workspace_id), class_id, term_id, document_id=document_id,
                          offset=offset, snapshot=snapshot)

    @routes.get(base + '/{document_id}/revisions/{version}', response_model=RevisionResponse)
    def revision(workspace_id: UUID, class_id: UUID, term_id: UUID, document_id: UUID, version: Version, request: Request):
        return {'document_id': document_id, 'workspace_id': workspace_id, 'class_id': class_id, 'term_id': term_id,
                'data': query.revision(*credentials(request, workspace_id), class_id, term_id, document_id, version)}

    return routes
