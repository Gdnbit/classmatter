"""A2A SDK messages/JSON-RPC client and standard EdDSA JWT peer proofs.

Only the SendMessage subset is admitted. There is no agent discovery, remote
tool dispatch, filesystem access, arbitrary callback URL or external fetch.
"""
from datetime import datetime, timezone
import json
from uuid import UUID

from a2a.types import AgentCard, Message, Part, SendMessageRequest
from a2a.client.transports.jsonrpc import JsonRpcTransport
from google.protobuf.json_format import MessageToDict, ParseDict
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
import httpx
import jwt
import rfc8785

from class_os.domain.collaboration import MaterialMessage, endpoint


MEDIA_TYPE = 'application/vnd.classmatter.material+json'


class LimitedStream(httpx.AsyncByteStream):
    def __init__(self,stream):
        self.stream=stream

    async def __aiter__(self):
        size=0
        async for chunk in self.stream:
            size+=len(chunk)
            if size>65536:
                raise ValueError('Material receipt exceeds byte limit')
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class LimitedTransport(httpx.AsyncBaseTransport):
    def __init__(self,transport=None):
        self.inner=transport or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self,request):
        response=await self.inner.handle_async_request(request)
        response.stream=LimitedStream(response.stream)
        return response

    async def aclose(self):
        await self.inner.aclose()


def unique(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('Duplicate message field')
        value[key] = item
    return value


def message(value, message_id, *, reply=False):
    return Message(message_id=str(message_id),role=2 if reply else 1,
        parts=[Part(text=json.dumps(value,ensure_ascii=False,separators=(',',':')),media_type=MEDIA_TYPE)])


def read_message(value, *, reply=False):
    if (value.role!=(2 if reply else 1) or len(value.parts)!=1 or value.parts[0].media_type!=MEDIA_TYPE
            or not value.parts[0].text or len(value.parts[0].text.encode())>65536
            or value.context_id or value.task_id or value.extensions or value.reference_task_ids
            or value.metadata):
        raise ValueError('Bounded material message required')
    part = value.parts[0]
    if part.raw or part.url or part.HasField('data') or part.metadata or part.filename:
        raise ValueError('Only one inert text part is supported')
    return json.loads(part.text,object_pairs_hook=unique)


class PeerProofs:
    def __init__(self, business, query, codec, *, clock=lambda:datetime.now(timezone.utc)):
        self.business,self.query,self.codec,self.clock = business,query,codec,clock

    def prepare(self,credentials):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes_raw().hex()
        packet = rfc8785.dumps({'workspace_id':str(credentials[3]),'public_key':public,
            'private_key':private.private_bytes_raw().hex()})
        return self.business.identity_key(credentials,public,self.codec(packet))

    def sign(self,credentials,receiver,message_id,payload_hash):
        row = self.query.key(credentials)
        if row is None:
            raise ValueError('Local collaboration identity is not ready')
        data = json.loads(self.codec(bytes(row['sealed_key']),decrypt=True),object_pairs_hook=unique)
        if (set(data)!={'workspace_id','public_key','private_key'} or data['workspace_id']!=str(credentials[3])
                or data['public_key']!=row['public_key']):
            raise ValueError('Wrong local key binding')
        private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(data['private_key']))
        if private.public_key().public_bytes_raw().hex()!=row['public_key']:
            raise ValueError('Wrong local signing key')
        now = int(self.clock().timestamp())
        return jwt.encode({'iss':str(credentials[3]),'aud':str(receiver),'jti':str(message_id),
            'iat':now,'exp':now+60,'digest':payload_hash},private,algorithm='EdDSA',headers={'typ':'JWT'})

    def verify(self,token,peer,receiver,message_id,payload_hash):
        if type(token) is not str or not 1<=len(token)<=4096:
            raise ValueError('Bounded peer proof required')
        header = jwt.get_unverified_header(token)
        if set(header)!={'alg','typ'} or header!={'alg':'EdDSA','typ':'JWT'}:
            raise ValueError('Pinned EdDSA proof required')
        value = jwt.decode(token,Ed25519PublicKey.from_public_bytes(bytes.fromhex(peer['public_key'])),
            algorithms=['EdDSA'],issuer=str(peer['peer_id']),audience=str(receiver),
            options={'require':['iss','aud','jti','iat','exp','digest'],'verify_exp':False,'verify_iat':False})
        now = int(self.clock().timestamp())
        if (set(value)!={'iss','aud','jti','iat','exp','digest'} or value['jti']!=str(message_id)
                or value['digest']!=payload_hash or type(value['iat']) is not int or type(value['exp']) is not int
                or not value['iat']<=now<value['exp']<=value['iat']+60):
            raise ValueError('Expired or mismatched peer proof')


class A2AMaterialTransport:
    def __init__(self,proofs,*,http_transport=None):
        self.proofs,self.http_transport = proofs,http_transport

    async def send(self,credentials,peer,value):
        url = endpoint(peer['endpoint'])+'/api/collaboration/a2a'
        proof = self.proofs.sign(credentials,peer['peer_id'],value.message_id,value.digest())
        async with httpx.AsyncClient(timeout=httpx.Timeout(8),follow_redirects=False,trust_env=False,
                transport=LimitedTransport(self.http_transport),headers={'Authorization':'Bearer '+proof}) as http:
            client = JsonRpcTransport(http,AgentCard(),url,is_shared_httpx=True)
            response = await client.send_message(SendMessageRequest(message=message(value.model_dump(mode='json'),value.message_id)))
        if not response.HasField('message') or response.HasField('task'):
            raise ValueError('Durable material receipt required')
        receipt = read_message(response.message,reply=True)
        if (set(receipt)!={'kind','message_id','payload_hash','proof'} or receipt['kind']!='classmatter.material-receipt.v1'
                or receipt['message_id']!=str(value.message_id) or receipt['payload_hash']!=value.digest()
                or response.message.message_id!=str(value.message_id)):
            raise ValueError('Wrong material receipt')
        self.proofs.verify(receipt['proof'],peer,credentials[3],value.message_id,value.digest())
        return receipt


def decode_request(body):
    if (type(body) is not dict or set(body)!={'jsonrpc','id','method','params'} or body['jsonrpc']!='2.0'
            or body['method']!='SendMessage' or type(body['id']) is not str or len(body['id'])>80):
        raise ValueError('Only bounded A2A SendMessage is supported')
    request = ParseDict(body['params'],SendMessageRequest(),ignore_unknown_fields=False)
    if request.tenant or request.metadata or request.HasField('configuration'):
        raise ValueError('Unsupported A2A options')
    value = MaterialMessage.model_validate(read_message(request.message))
    if request.message.message_id!=str(value.message_id):
        raise ValueError('Mismatched A2A message identity')
    return value


def receipt_response(rpc_id,value,proof):
    receipt = {'kind':'classmatter.material-receipt.v1','message_id':str(value.message_id),
               'payload_hash':value.digest(),'proof':proof}
    return {'jsonrpc':'2.0','id':rpc_id,'result':{'message':MessageToDict(message(receipt,value.message_id,reply=True))}}
