"""Closed values and official SDK wire round trips; no external service or data."""
from uuid import uuid4
import pytest
from google.protobuf.json_format import MessageToDict
from a2a.types import SendMessageRequest

from class_os.domain.collaboration import Invitation,MaterialMessage,RequestMaterial,ShareMaterial,SaveCollectedSummary,decode_collaboration
from class_os.domain.workspace_chat import candidate
from class_os.infrastructure.collaboration_transport import message,decode_request,read_message,unique


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
