"""Human contact setup and a fixed authenticated A2A material ingress."""
from datetime import datetime
import json
from typing import Literal
from uuid import UUID

import anyio
import jwt
from google.protobuf.json_format import ParseError
from fastapi import APIRouter,Request,HTTPException
from pydantic import Field,model_validator

from class_os.domain.collaboration import Invitation,decode_collaboration
from class_os.application.identity import IdentityDenied
from class_os.application.roster import CommandRejected
from class_os.infrastructure.collaboration_transport import decode_request,receipt_response,unique
from .contracts import WireModel
from .roster import credentials
from .classroom_work import ClassroomScope


class MaterialRequest(ClassroomScope):
    command: Literal['collaboration.request']
    request_id: UUID
    peer_id: UUID
    thread_id: UUID
    title: str = Field(min_length=1,max_length=80)
    body: str = Field(min_length=1,max_length=1000)


class MaterialShare(ClassroomScope):
    command: Literal['collaboration.material.share']
    message_id: UUID
    request_id: UUID
    peer_id: UUID
    thread_id: UUID
    document_id: UUID
    expected_version: int = Field(strict=True,ge=1)
    title: str = Field(min_length=1,max_length=80)
    body: str = Field(min_length=1,max_length=12000)


class CollectedSummary(ClassroomScope):
    command: Literal['collaboration.summary.save']
    request_id: UUID
    source_message_id: UUID
    document_id: UUID
    expected_version: int = Field(strict=True,ge=0)
    title: Literal['班级工作小结']
    body: str = Field(max_length=100000)
    format: Literal['markdown'] = 'markdown'


class InviteBody(WireModel):
    name: str = Field(min_length=1,max_length=80)


class InviteResult(WireModel):
    schema_version: Literal['classmatter.collaboration-invitation.v1'] = 'classmatter.collaboration-invitation.v1'
    invitation: Invitation


class AddPeer(ClassroomScope):
    invitation: Invitation


class Peer(WireModel):
    peer_id: UUID
    name: str = Field(min_length=1,max_length=80)
    endpoint: str = Field(max_length=128)
    public_key: str = Field(pattern=r'^[a-f0-9]{64}$')
    class_id: UUID
    term_id: UUID
    status: Literal['active','revoked']
    version: int = Field(strict=True,ge=1)


class Saved(WireModel):
    request_id: UUID
    document_id: UUID
    document_version: int = Field(strict=True,ge=1)


class MaterialItem(WireModel):
    message_id: UUID
    request_id: UUID
    peer_id: UUID
    direction: Literal['incoming','outgoing']
    operation: Literal['request','material']
    title: str = Field(min_length=1,max_length=80)
    body: str = Field(min_length=1,max_length=12000)
    source_document_id: UUID | None
    source_version: int | None = Field(ge=1)
    class_id: UUID
    term_id: UUID
    thread_id: UUID
    created_at: datetime
    delivered_at: datetime | None
    peer_name: str = Field(max_length=80)
    status: Literal['queued','retry-needed','delivered','received','material-received','material-sent','saved']
    saved: Saved | None


class CollaborationState(WireModel):
    schema_version: Literal['classmatter.collaboration-state.v1'] = 'classmatter.collaboration-state.v1'
    peers: list[Peer] = Field(max_length=20)
    items: list[MaterialItem] = Field(max_length=100)


class RevokePeer(WireModel):
    expected_version: int = Field(strict=True,ge=1)


class RetryDelivery(WireModel):
    pass


def router(service,personal):
    routes = APIRouter()
    base = '/api/workspaces/{workspace_id}/collaboration'

    @routes.get(base,response_model=CollaborationState)
    def state(workspace_id: UUID,request: Request):
        return service.query.read(credentials(request,workspace_id))

    @routes.get(base+'/threads/{thread_id}',response_model=CollaborationState)
    def thread_state(workspace_id: UUID,thread_id: UUID,request: Request):
        return service.query.read(credentials(request,workspace_id),thread_id=thread_id)

    @routes.post(base+'/invitation',response_model=InviteResult)
    async def invitation(workspace_id: UUID,request: Request,body: InviteBody):
        auth = credentials(request,workspace_id,write=True)
        value = await service.invitation(auth,body.name,str(request.base_url).rstrip('/'))
        await personal.watch(auth)
        return InviteResult(invitation=value)

    @routes.post(base+'/peers',response_model=Peer)
    async def add_peer(workspace_id: UUID,request: Request,body: AddPeer):
        auth = credentials(request,workspace_id,write=True)
        value = await anyio.to_thread.run_sync(lambda:service.business.add_peer(auth,body.invitation,body.class_id,body.term_id))
        await personal.watch(auth)
        return value

    @routes.post(base+'/peers/{peer_id}/revoke',response_model=Peer)
    def revoke(workspace_id: UUID,peer_id: UUID,request: Request,body: RevokePeer):
        return service.business.revoke_peer(credentials(request,workspace_id,write=True),peer_id,body.expected_version)

    @routes.post(base+'/messages/{message_id}/retry',response_model=CollaborationState)
    async def retry(workspace_id: UUID,message_id: UUID,request: Request,body: RetryDelivery):
        auth=credentials(request,workspace_id,write=True)
        await anyio.to_thread.run_sync(lambda:service.business.retry(auth,message_id))
        await personal.watch(auth)
        return service.query.read(auth)

    @routes.post('/api/collaboration/a2a')
    async def receive(request: Request):
        # Peer proofs do not use browser cookies. Nothing on this route can
        # query a class, approve a change, fetch a URL, or call a model.
        if request.headers.get('origin') or request.headers.get('cookie'):
            raise HTTPException(403)
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>65536:
                raise HTTPException(413)
            raw.extend(chunk)
        try:
            body = json.loads(raw,object_pairs_hook=unique)
            value = decode_request(body)
            auth = request.headers.getlist('authorization')
            if len(auth)!=1 or not auth[0].startswith('Bearer '):
                raise ValueError('Peer proof required')
            proof = await service.receive(value,auth[0][7:])
            return receipt_response(body['id'],value,proof)
        except IdentityDenied:
            raise HTTPException(503) from None
        except (ValueError,CommandRejected,TypeError,KeyError,jwt.PyJWTError,ParseError):
            raise HTTPException(403) from None
    return routes
