"""Small durable-delivery coordinator. APScheduler is owned by the existing service."""
import asyncio
import logging

import anyio

from class_os.application.collaboration import CollaborationBusinessGateway,CollaborationQueryGateway
from class_os.application.identity import IdentityDenied
from class_os.application.roster import CommandRejected
from class_os.domain.collaboration import Invitation,endpoint
from .collaboration_transport import PeerProofs,A2AMaterialTransport


class CollaborationService:
    def __init__(self,runtime,*,transport_factory=A2AMaterialTransport):
        self.runtime = runtime
        self.business = CollaborationBusinessGateway(runtime.business.identity,runtime.business.store,clock=runtime.business.clock)
        self.query = CollaborationQueryGateway(runtime.query.identity,runtime.query.store,clock=runtime.query.clock)
        codec = runtime.business.store.restrictions.codec
        self.proofs = PeerProofs(self.business,self.query,codec,clock=runtime.business.clock)
        self.transport = transport_factory(self.proofs)
        self.sessions,self.checking = {},set()

    async def watch(self,credentials):
        await anyio.to_thread.run_sync(lambda:self.query.read(credentials))
        self.sessions[credentials[3]] = credentials

    async def invitation(self,credentials,name,address):
        address = endpoint(address)
        row = await anyio.to_thread.run_sync(lambda:self.proofs.prepare(credentials))
        await self.watch(credentials)
        return Invitation(workspace_id=credentials[3],name=name,endpoint=address,public_key=row['public_key'])

    async def receive(self,value,proof):
        credentials = self.sessions.get(value.receiver)
        if credentials is None:
            raise IdentityDenied()
        state = await anyio.to_thread.run_sync(lambda:self.query.read(credentials))
        peer = next((p for p in state['peers'] if p['peer_id']==value.sender and p['status']=='active'),None)
        if peer is None:
            raise ValueError('Peer was not confirmed locally')
        self.proofs.verify(proof,peer,value.receiver,value.message_id,value.digest())
        await anyio.to_thread.run_sync(lambda:self.business.receive(credentials,value))
        # Sign only after the inbound transaction and its audit committed.
        return await anyio.to_thread.run_sync(lambda:self.proofs.sign(credentials,value.sender,value.message_id,value.digest()))

    async def check(self,workspace_id):
        if workspace_id in self.checking or workspace_id not in self.sessions:
            return
        self.checking.add(workspace_id)
        credentials = self.sessions[workspace_id]
        try:
            state = await anyio.to_thread.run_sync(lambda:self.query.read(credentials))
            for row in state['items']:
                if row['direction']!='outgoing' or row['delivered_at']:
                    continue
                try:
                    ticket = await anyio.to_thread.run_sync(lambda:self.business.attempt(credentials,row['message_id']))
                except CommandRejected:
                    # A revoked contact or closed thread retains its history,
                    # but cannot starve independent still-authorized work.
                    continue
                if ticket is None:
                    continue
                try:
                    await self.transport.send(credentials,ticket['peer'],ticket['message'])
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logging.getLogger(__name__).info('Material delivery pending: %s',type(error).__name__)
                    continue  # Retry is a later persisted attempt, never another model run.
                await anyio.to_thread.run_sync(lambda:self.business.delivered(credentials,row['message_id'],ticket['message'].digest()))
            if self.runtime.sdk.provider_state and self.runtime.sdk.provider_state(credentials)=='configured-api':
                state = await anyio.to_thread.run_sync(lambda:self.query.read(credentials))
                for row in state['items']:
                    if row['direction']=='incoming' and row['operation']=='material' and not row['saved']:
                        turn = await anyio.to_thread.run_sync(lambda:self.runtime.query.turn(credentials,row['thread_id'],row['message_id']))
                        if turn[0]['status']=='active' and turn[1]['state']=='queued':
                            async for _ in self.runtime.stream_queued(credentials,row['thread_id'],row['message_id']):
                                pass
        except IdentityDenied:
            self.sessions.pop(workspace_id,None)
        finally:
            self.checking.discard(workspace_id)
