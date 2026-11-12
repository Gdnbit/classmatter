"""Actual ISB/QG/PG export; no business write or unscoped renderer access."""
from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import pytest
from docx import Document
from pptx import Presentation
from sqlalchemy import text

from class_os.domain.documents import ReviseDocument
from test_documents_http import client_for, paths
from test_documents_gateway import documents, control, storage, roster, identity, create, saved


@pytest.mark.db
async def test_exports_bind_saved_scope_version_and_never_create_business_revisions(documents):
    command = replace(create(documents), body='# 课堂目标\n认识分数。\n# 课堂练习\n合成练习题。')
    saved(documents, command)
    _, collection = paths(documents, command)
    path = collection + f'/{command.document_id}/exports/1/'
    async with client_for(documents) as client:
        for format in ('docx', 'pptx'):
            response = await client.get(path + format)
            assert response.status_code == 200, response.text if response.status_code != 200 else ''
            assert response.headers['x-classmatter-document-id'] == str(command.document_id)
            assert response.headers['x-classmatter-document-version'] == '1'
            assert response.headers['content-disposition'].endswith('.' + format)
            assert response.headers['cache-control'] == 'no-store'
            if format == 'docx':
                assert '认识分数。' in [p.text for p in Document(BytesIO(response.content)).paragraphs]
            else:
                assert Presentation(BytesIO(response.content)).slides[1].shapes[0].text == '课堂目标'
        assert (await client.get(path + 'pdf')).status_code == 400
        assert (await client.get(path.replace('/exports/1/', '/exports/0/') + 'docx')).status_code == 400
        assert (await client.get(path.replace(str(command.class_id), str(uuid4())) + 'docx')).status_code == 409
        saved(documents, ReviseDocument(command.document_id, command.class_id, command.term_id, 1, command.title, '已核对的新正文'))
        assert (await client.get(path + 'docx')).status_code == 409
        latest = await client.get(path.replace('/exports/1/', '/exports/2/') + 'docx')
        assert latest.status_code == 200
        assert Document(BytesIO(latest.content)).paragraphs[1].text == '已核对的新正文'
        client.cookies.clear()
        assert (await client.get(path + 'docx')).status_code == 401
    with documents[3].transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document')).scalar_one() == 1
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document_revision')).scalar_one() == 2
        assert connection.execute(text('SELECT count(*) FROM class_os.export_job')).scalar_one() == 0
