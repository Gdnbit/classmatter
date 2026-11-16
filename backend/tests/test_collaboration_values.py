"""Closed values and official SDK wire round trips; no external service or data."""
from uuid import uuid4
import pytest
from google.protobuf.json_format import MessageToDict
from a2a.types import SendMessageRequest

from class_os.domain.collaboration import Invitation,MaterialMessage,RequestMaterial,ShareMaterial,SaveCollectedSummary,decode_collaboration
from class_os.domain.workspace_chat import candidate
from class_os.infrastructure.collaboration_transport import message,decode_request,read_message,unique
from class_os.infrastructure.collaboration_tools import explicit_material_reply


@pytest.mark.parametrize('utterance,expected',[
    ('把《本周教学进度》提供给合成李老师。',True),
    ('请提供本周教学进度给合成李老师。',True),
    ('帮我将《本周教学进度》分享给合成李老师！',True),
    ('先修改《本周教学进度》，然后提供给合成李老师。',False),
    ('不要把《本周教学进度》提供给合成李老师。',False),
    ('请提供修改后的本周教学进度给合成李老师。',False),
    ('把《本周教学进度》提供给另一位老师。',False),
    ('《本周教学进度》写了什么？',False),
])
def test_share_only_scope_uses_current_literal_intent_and_pending_local_request(utterance,expected):
    item=dict(direction='incoming',operation='request',status='received',peer_name='合成李老师')
    assert explicit_material_reply(utterance,{'items':[item]}) is expected
    assert explicit_material_reply(utterance,{'items':[item|{'status':'material-sent'}]}) is expected
    for changes in ({'direction':'outgoing'},{'operation':'material'},{'status':'stopped'}):
        assert not explicit_material_reply(utterance,{'items':[item|changes]})


def test_share_only_candidate_boundary_refuses_document_edit_even_if_provider_ignores_tools():
    from pydantic_ai import ModelRetry
    from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
    from class_os.domain.documents import ReviseDocument
    capture=WorkspaceActionCapture(('把《进度》提供给合成李老师。',),collaboration_reply_only=True)
    with pytest.raises(ModelRetry,match='only shares'):
        capture.propose(ReviseDocument(uuid4(),uuid4(),uuid4(),1,'进度','invented material','markdown'))
    assert capture.proposed is None


def test_closed_commands_and_official_a2a_message_roundtrip():
    root,peer,c,t,thread,document = [uuid4() for _ in range(6)]
    for command in (RequestMaterial(root,peer,c,t,thread,'本周教学进度','请提供本周数学教学进度'),
                    ShareMaterial(uuid4(),root,peer,c,t,thread,document,1,'数学教学进度','完成第三单元'),
                    SaveCollectedSummary(root,uuid4(),document,c,t,0,'班级工作小结','本周完成第三单元')):
        assert decode_collaboration(command.canonical())==command
        assert candidate(command.canonical())==command
        with pytest.raises(ValueError):
            decode_collaboration(command.canonical()|{'arbitrary_sql':'not executable'})
    value = MaterialMessage(message_id=root,request_id=root,sender=uuid4(),receiver=peer,
        operation='request',title='本周教学进度',body='请提供本周数学教学进度')
    wire = {'jsonrpc':'2.0','id':str(uuid4()),'method':'SendMessage',
            'params':MessageToDict(SendMessageRequest(message=message(value.model_dump(mode='json'),root)))}
    assert decode_request(wire)==value
    wire['params']['metadata']={'arbitrary_tool':'not executable'}
    with pytest.raises(ValueError):
        decode_request(wire)


@pytest.mark.parametrize('address',['http://example.com','https://127.0.0.1:8001','http://127.0.0.1:8001/path',
    'http://127.0.0.1:8001?url=remote','http://user@127.0.0.1:8001','http://localhost:8001'])
def test_first_slice_never_exposes_or_follows_external_endpoints(address):
    with pytest.raises(ValueError):
        Invitation(workspace_id=uuid4(),name='合成王老师',endpoint=address,public_key='ab'*32)


def test_material_provenance_and_unknown_fields_are_not_optional():
    root,sender,receiver = uuid4(),uuid4(),uuid4()
    data = dict(message_id=uuid4(),request_id=root,sender=sender,receiver=receiver,
                operation='material',title='教学进度',body='完成第三单元',source_document_id=uuid4(),source_version=1)
    value = MaterialMessage(**data)
    assert value.digest()!=MaterialMessage(**(data|{'body':'完成第四单元'})).digest()
    for changes in ({'source_version':True},{'source_version':None},{'message_id':root},
                    {'receiver':sender},{'tool':'execute'}, {'body':'a'*12001}):
        with pytest.raises(ValueError):
            MaterialMessage(**(data|changes))
    with pytest.raises(ValueError):
        unique([('body','one'),('body','two')])


async def test_receipt_stream_has_a_hard_byte_bound():
    import httpx
    from class_os.infrastructure.collaboration_transport import LimitedStream
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'x'*65000
            yield b'x'*1000
    received=0
    with pytest.raises(ValueError,match='byte limit'):
        async for chunk in LimitedStream(Chunks()):
            received+=len(chunk)
    assert received==65000


@pytest.mark.parametrize('changes',[{'exp':1000},{'iat':1001},{'exp':1061},
    {'aud':str(uuid4())},{'jti':str(uuid4())},{'digest':'b'*64},{'remote_tool':'not executable'}])
def test_even_a_valid_peer_signature_does_not_override_receipt_scope_or_expiry(changes):
    from datetime import datetime,timezone
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from class_os.infrastructure.collaboration_transport import PeerProofs
    import jwt
    sender,receiver,message_id=uuid4(),uuid4(),uuid4()
    key=Ed25519PrivateKey.generate()
    peer={'peer_id':sender,'public_key':key.public_key().public_bytes_raw().hex()}
    proofs=PeerProofs(None,None,None,clock=lambda:datetime.fromtimestamp(1000,timezone.utc))
    claims={'iss':str(sender),'aud':str(receiver),'jti':str(message_id),'iat':1000,'exp':1060,'digest':'a'*64}
    valid=jwt.encode(claims,key,algorithm='EdDSA')
    proofs.verify(valid,peer,receiver,message_id,'a'*64)
    altered=jwt.encode(claims|changes,key,algorithm='EdDSA')
    with pytest.raises((ValueError,jwt.PyJWTError)):
        proofs.verify(altered,peer,receiver,message_id,'a'*64)
