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


@pytest.mark.parametrize('output', ['docx', 'pptx'])
def test_work_summary_markdown_is_formatted_and_retains_code_and_sources(output):
    body = '# 合成工作小结\n\n* **事实记录**：合成学生甲交来展示作品。\n* *下一步*：核对材料。\n\n3. 收齐回执\n4. 核对人数\n\n[通知](https://fixture.invalid/notice)\n\n`**保持原样**`\n\n```text\nx < 2\n**不是加粗**\n```'
    value = render_office('合成工作小结', body, 'markdown', output)
    if output == 'docx':
        document = Document(BytesIO(value.content))
        paragraphs = document.paragraphs
        texts = [paragraph.text for paragraph in paragraphs]
        assert texts.count('合成工作小结') == 1
        assert '• 事实记录：合成学生甲交来展示作品。' in texts
        assert '• 下一步：核对材料。' in texts
        assert '3. 收齐回执' in texts and '4. 核对人数' in texts
        assert '通知 (https://fixture.invalid/notice)' in texts
        assert '**保持原样**' in texts and '**不是加粗**' in texts and 'x < 2' in texts
        assert any(run.bold is True and run.text == '事实记录' for paragraph in paragraphs for run in paragraph.runs)
        assert any(run.italic is True and run.text == '下一步' for paragraph in paragraphs for run in paragraph.runs)
        assert any(run.font.name == 'Consolas' and run.text == '**保持原样**' for paragraph in paragraphs for run in paragraph.runs)
        from docx.oxml.ns import qn
        for name in ('Normal', 'Title', 'Quote', 'Heading 1', 'Heading 6'):
            fonts = document.styles[name].element.get_or_add_rPr().findall(qn('w:rFonts'))
            assert len(fonts) == 1 and fonts[0].get(qn('w:eastAsia')) == 'Microsoft YaHei'
            assert all('theme' not in attribute.lower() for attribute in fonts[0].attrib)
    else:
        presentation = Presentation(BytesIO(value.content))
        texts = '\n'.join(shape.text for slide in presentation.slides for shape in slide.shapes if shape.has_text_frame)
        assert '* **事实记录**' not in texts and '• 事实记录：合成学生甲交来展示作品。' in texts
        assert '3. 收齐回执' in texts and '4. 核对人数' in texts
        assert '通知 (https://fixture.invalid/notice)' in texts.replace('\n', '')
        assert '**保持原样**' in texts and '**不是加粗**' in texts and 'x < 2' in texts
        runs = [run for slide in presentation.slides for shape in slide.shapes if shape.has_text_frame for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
        assert any(run.font.bold is True and run.text == '事实记录' for run in runs)
        assert any(run.font.italic is True and run.text == '下一步' for run in runs)
    with zipfile.ZipFile(BytesIO(value.content)) as archive:
        assert all(b'TargetMode="External"' not in archive.read(name) for name in archive.namelist() if name.endswith('.rels'))


@pytest.mark.parametrize('output', ['docx', 'pptx'])
def test_plain_text_stays_literal_including_markdown_characters(output):
    body = '* **按原样保留**\n# 不是标题\n`不是代码格式`'
    value = render_office('合成纯文字', body, 'plain-text', output)
    if output == 'docx':
        assert [paragraph.text for paragraph in Document(BytesIO(value.content)).paragraphs][1:] == body.split('\n')
    else:
        deck = Presentation(BytesIO(value.content))
        assert '\n'.join(slide.shapes[1].text for slide in list(deck.slides)[1:]) == body


def test_markdown_nested_lists_wrapped_styles_and_text_only_images():
    from class_os.infrastructure.office_markdown import blocks, wrapped_runs
    body = '* **第一项**\n  * 子项目\n\n![作品](https://fixture.invalid/no-fetch.png)\n\n> 引用原话\n\n**' + '合成文字' * 50 + '**'
    parsed = blocks(body, 'markdown')
    assert parsed[0].text == '• 第一项' and parsed[0].depth == 1
    assert parsed[1].text == '• 子项目' and parsed[1].depth == 2
    assert parsed[2].text == '[作品] (https://fixture.invalid/no-fetch.png)'
    assert parsed[3].quoted and parsed[3].text == '引用原话'
    wrapped = list(wrapped_runs(parsed[4]))
    assert ''.join(span.text for line in wrapped for span in line) == '合成文字' * 50
    assert all(span.bold for line in wrapped for span in line)
    artifact = render_office('合成无外部资源', body, 'markdown', 'docx')
    with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
        assert not any(name.startswith('word/media/') for name in archive.namelist())
        assert all(b'TargetMode="External"' not in archive.read(name) for name in archive.namelist() if name.endswith('.rels'))


def test_excessive_paragraphs_reject_before_office_file_success():
    with pytest.raises(ArtifactTooLarge):
        render_office('合成超多段落', '\n' * 10001, 'plain-text', 'docx')


def test_blank_list_items_do_not_renumber_later_teacher_instructions():
    from class_os.infrastructure.office_markdown import blocks
    assert [block.text for block in blocks('1.\n2. 核对材料', 'markdown')] == ['1. ', '2. 核对材料']
    assert [block.text for block in blocks('*\n* 核对材料', 'markdown')] == ['• ', '• 核对材料']
    assert [(block.text, block.depth) for block in blocks('1.\n   * 子项\n2. 次项', 'markdown')] == [('1. ', 1), ('• 子项', 2), ('2. 次项', 1)]


@pytest.mark.parametrize('output', ['docx', 'pptx'])
def test_nested_numbering_quotes_and_rich_files_remain_editable(output):
    body = '7. 第一项\n   * 子项目\n8. 第二项\n\n> **保留原话**\n\n*\n  ```text\n  **代码原文**\n  ```\n\n\\*原样星号\\*'
    value = render_office('合成排版验收', body, 'markdown', output)
    changed = BytesIO()
    if output == 'docx':
        document = Document(BytesIO(value.content))
        paragraphs = document.paragraphs
        assert [paragraph.text for paragraph in paragraphs][1:] == ['7. 第一项', '• 子项目', '8. 第二项', '保留原话', '• **代码原文**', '*原样星号*']
        assert paragraphs[4].style.name == 'Quote'
        document.add_paragraph('合成后续编辑')
        document.save(changed)
        assert Document(BytesIO(changed.getvalue())).paragraphs[-1].text == '合成后续编辑'
    else:
        deck = Presentation(BytesIO(value.content))
        text = '\n'.join(slide.shapes[1].text for slide in list(deck.slides)[1:])
        assert '7. 第一项\n• 子项目\n8. 第二项' in text
        assert '› 保留原话' in text and '• **代码原文**' in text and '*原样星号*' in text
        paragraph = deck.slides[-1].shapes[1].text_frame.add_paragraph()
        paragraph.text = '合成后续编辑'
        deck.save(changed)
        assert Presentation(BytesIO(changed.getvalue())).slides[-1].shapes[1].text_frame.paragraphs[-1].text == '合成后续编辑'
