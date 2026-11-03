"""Document wire contracts backed by disposable real ISB/BCG/QG/PostgreSQL."""
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from class_os.domain.documents import ReviseDocument
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.documents import DocumentCreate, DocumentRevise, DocumentState
from class_os.interfaces.http.settings import Settings
from test_documents_gateway import documents, control, storage, roster, identity, create, saved


def app_for(data):
    return create_app(Settings(), identity=data[0].identity, document_business=data[0], document_query=data[1])


def client_for(data, *, app=None):
    transport = httpx.ASGITransport(app=app or app_for(data), client=('127.0.0.1', 12345), raise_app_exceptions=False)
    client = httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:8000')
    for name, content in zip(('session', 'client', 'csrf'), data[5][6][:3]):
        client.cookies.set('class_os_' + name, content, path='/api')
    return client


def paths(data, command):
    root = f'/api/workspaces/{data[5][6][3]}'
    return root + '/document-commands', root + f'/classes/{command.class_id}/terms/{command.term_id}/documents'


def headers(data):
    return {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': data[5][6][2]}


@pytest.mark.db
async def test_http_large_draft_preview_commit_receipt_and_application_reopen(documents):
    command = replace(create(documents), body='合成内容\n' * 20000)
    write, listing = paths(documents, command)
    async with client_for(documents) as client:
        assert (await client.get(listing)).json()['data'] == []
        assert (await client.post(write + '/preview', json=command.canonical())).status_code == 403
        proposal = await client.post(write + '/preview', json=command.canonical(), headers=headers(documents))
        assert proposal.status_code == 200, proposal.text
        view = proposal.json()
        assert view['schema_version'] == 'classmatter.document-preview.v1' and view['risk'] == 'W2'
        assert view['payload'] == command.canonical()
        commit = {'proposal_id': view['proposal_id'], 'idempotency_key': str(uuid4())}
        assert (await client.post(write + '/commit', json=commit, headers=headers(documents))).status_code == 409
        approval = await client.post(write + '/approve', json={'proposal_id': view['proposal_id'],
            'payload_hash': view['payload_hash']}, headers=headers(documents))
        assert approval.status_code == 200, approval.text
        commit['approval'] = approval.json()['approval']
        result = await client.post(write + '/commit', json=commit, headers=headers(documents))
        assert result.status_code == 200, result.text
        assert result.json()['resource_id'] == str(command.document_id)
        assert (await client.post(write + '/commit', json=commit, headers=headers(documents))).json() == result.json()
        status = await client.get(write + f"/{view['proposal_id']}/receipts/{commit['idempotency_key']}")
        assert status.json()['status'] == 'committed'
        assert status.json()['receipt']['receipt_id'] == result.json()['receipt_id']
    async with client_for(documents, app=app_for(documents)) as reopened:
        response = await reopened.get(listing + f'/{command.document_id}')
        assert response.status_code == 200, response.text
        assert response.json()['content_authority'] == 'working-draft'
        assert response.json()['data']['body'] == command.body
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
        items = (await reopened.get(listing)).json()['data']
        assert len(items) == 1 and 'body' not in items[0]


@pytest.mark.db
async def test_http_identity_scope_closed_fields_and_body_exemptions(documents):
    command = create(documents)
    saved(documents, command)
    write, listing = paths(documents, command)
    async with client_for(documents) as client:
        foreign = listing.replace(str(documents[5][6][3]), str(uuid4()))
        response = await client.get(foreign)
        assert response.status_code == 401 and command.title not in response.text
        response = await client.get(listing.replace(str(command.class_id), str(uuid4())) + f'/{command.document_id}')
        assert response.status_code == 409 and command.body not in response.text
        for field, value in (('risk', 'W1'), ('authority', 'verified-fact'), ('sql', 'SELECT 1')):
            response = await client.post(write + '/preview', json={**command.canonical(), field: value}, headers=headers(documents))
            assert response.status_code == 400
        for body in ('\x00', 'a' * 100001):
            response = await client.post(write + '/preview', json=replace(command, document_id=uuid4(), body='').canonical() | {'body': body},
                                         headers=headers(documents))
            assert response.status_code == 400
        response = await client.post(write + '/preview', content=b'{' + b'x' * (640 * 1024), headers=headers(documents))
        assert response.status_code == 400 and len(response.content) < 1000
        duplicate = '{"command":"document.create","command":"document.archive"}'
        assert (await client.post(write + '/preview', content=duplicate, headers=headers(documents))).status_code == 400
        # Other registered endpoints retain the original 8KiB envelope limit.
        assert (await client.post(write + '/approve', content=' ' * 8193, headers=headers(documents))).status_code == 400
        assert (await client.get(listing + '?offset=0')).status_code == 400
    async with client_for(documents, app=create_app(Settings(), identity=documents[0].identity)) as disabled:
        assert (await disabled.get(listing)).status_code == 404
        assert (await disabled.post(write + '/preview', content=' ' * 8193, headers=headers(documents))).status_code == 400


@pytest.mark.db
@pytest.mark.parametrize('history', [False, True])
async def test_http_complete_metadata_paging_and_stale_snapshot_refusal(documents, history):
    command = create(documents)
    saved(documents, command)
    for index in range(50):
        change = ReviseDocument(command.document_id, command.class_id, command.term_id, index + 1,
            f'合成版本{index + 2}', '版本正文') if history else replace(command, document_id=uuid4(), title=f'合成文档{index}')
        saved(documents, change)
    _, listing = paths(documents, command)
    path = listing + f'/{command.document_id}/history' if history else listing
    async with client_for(documents) as client:
        response = await client.get(path)
        assert response.status_code == 200, response.text
        first = response.json()
        assert len(first['data']) == 50 and first['next_offset'] == 50
        assert all('body' not in row for row in first['data'])
        next_path = path + f"/pages/{first['snapshot']}/50"
        second = await client.get(next_path)
        assert second.status_code == 200, second.text
        assert len(second.json()['data']) == 1 and second.json()['next_offset'] is None
        key = 'version' if history else 'document_id'
        assert len({row[key] for row in first['data'] + second.json()['data']}) == 51
        if history:
            original = await client.get(listing + f'/{command.document_id}/revisions/1')
            assert original.json()['data']['body'] == command.body
            assert original.json()['document_id'] == str(command.document_id)
            change = ReviseDocument(command.document_id, command.class_id, command.term_id, 51, '合成版本52', '新正文')
        else:
            change = replace(command, document_id=uuid4(), title='合成新增文档')
        saved(documents, change)
        assert (await client.get(next_path)).status_code == 409
        assert (await client.get(path + f"/pages/{first['snapshot']}/51")).status_code == 400


@pytest.mark.db
async def test_http_audit_outage_never_releases_document_body(documents, monkeypatch):
    command = create(documents)
    saved(documents, command)
    _, listing = paths(documents, command)
    monkeypatch.setattr(documents[2], 'audit', lambda *args: None)
    async with client_for(documents) as client:
        response = await client.get(listing + f'/{command.document_id}')
        assert response.status_code == 503 and response.json()['error']['code'] == 'AUDIT_UNAVAILABLE'
        assert command.title not in response.text and 'data' not in response.json()


def test_document_contracts_and_optional_composition_are_closed():
    from pydantic import ValidationError
    command = {'command': 'document.create', 'document_id': str(uuid4()), 'class_id': str(uuid4()),
               'term_id': str(uuid4()), 'title': '合成文档', 'body': '', 'format': 'plain-text'}
    assert DocumentCreate.model_validate(command).body == ''
    for bad in ({**command, 'authority': 'fact'}, {**command, 'title': ' untrimmed '}, {**command, 'body': '\x00'}):
        with pytest.raises(ValidationError):
            DocumentCreate.model_validate(bad)
    with pytest.raises(ValidationError):
        DocumentRevise.model_validate({**command, 'command': 'document.revise', 'expected_version': True})
    with pytest.raises(ValidationError):
        DocumentState.model_validate({key: value for key, value in command.items() if key not in ('title', 'body', 'format')})
    with pytest.raises(ValueError, match='Document composition'):
        create_app(Settings(), document_query=object())
