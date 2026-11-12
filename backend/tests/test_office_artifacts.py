"""Actual OOXML generation, edit/reopen and bounded text pagination."""
from io import BytesIO
import zipfile

import pytest
from docx import Document
from pptx import Presentation

from class_os.infrastructure.office_artifacts import render_office, ArtifactTooLarge, MAX_SLIDES
from class_os.application.document_artifacts import MEDIA


@pytest.mark.parametrize('output', ['docx', 'pptx'])
def test_chinese_lesson_is_editable_ooxml_without_fetching_links(output):
    value = render_office('合成教案/草稿', '# 课堂目标\n认识分数。\n## 课堂活动\n学生分组讨论。\nhttps://fixture.invalid/不应访问', 'markdown', output)
    assert value.media_type == MEDIA[output] and value.filename == '合成教案_草稿.' + output
    with zipfile.ZipFile(BytesIO(value.content)) as archive:
        assert not any('vbaProject' in name or 'activeX' in name for name in archive.namelist())
        assert all(b'TargetMode="External"' not in archive.read(name) for name in archive.namelist() if name.endswith('.rels'))
    changed = BytesIO()
    if output == 'docx':
        document = Document(BytesIO(value.content))
        assert [p.text for p in document.paragraphs] == ['合成教案/草稿', '课堂目标', '认识分数。', '课堂活动', '学生分组讨论。', 'https://fixture.invalid/不应访问']
        assert document.paragraphs[1].style.name == 'Heading 1'
        document.paragraphs[2].text = '老师可以继续编辑。'
        document.save(changed)
        assert Document(BytesIO(changed.getvalue())).paragraphs[2].text == '老师可以继续编辑。'
    else:
        presentation = Presentation(BytesIO(value.content))
        assert len(presentation.slides) == 3
        assert presentation.slides[1].shapes[0].text == '课堂目标'
        assert '认识分数。' in presentation.slides[1].shapes[1].text
        presentation.slides[1].shapes[1].text = '老师可以继续编辑。'
        presentation.save(changed)
        assert Presentation(BytesIO(changed.getvalue())).slides[1].shapes[1].text == '老师可以继续编辑。'


def test_ppt_long_chinese_plain_text_and_title_are_not_silently_truncated():
    title = '合成班级教案' * 10
    body = '合成课堂讨论材料，尊重学生的不同观点并展示过程。' * 180
    value = render_office(title, body, 'plain-text', 'pptx')
    presentation = Presentation(BytesIO(value.content))
    assert 3 < len(presentation.slides) <= MAX_SLIDES
    assert presentation.slides[0].shapes[0].text.replace('\n', '') == title
    rendered = ''.join(slide.shapes[1].text.replace('\n', '') for slide in list(presentation.slides)[1:])
    assert rendered == body


def test_oversize_deck_is_rejected_before_partial_success():
    with pytest.raises(ArtifactTooLarge):
        render_office('合成超长课件', '学' * 100000, 'plain-text', 'pptx')
    for output in ('html', 'pdf', 'docx.exe'):
        with pytest.raises(ValueError):
            render_office('合成教案', '正文', 'plain-text', output)


def test_empty_document_exports_an_honest_editable_title_only():
    value = render_office('合成空白草稿', '', 'plain-text', 'pptx')
    presentation = Presentation(BytesIO(value.content))
    assert len(presentation.slides) == 1 and presentation.slides[0].shapes[0].text == '合成空白草稿'
