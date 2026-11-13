"""Replaceable text-only Office renderer. No model, network or business writes."""
from io import BytesIO
import re
from textwrap import wrap
from class_os.application.document_artifacts import ExportFormat, MEDIA, MAX_BYTES, ArtifactTooLarge, OfficeArtifact
from .office_markdown import Block, Run, blocks, wrapped_runs

MAX_SLIDES = 150


def render_office(title: str, body: str, format: str, output: ExportFormat) -> OfficeArtifact:
    if (output not in MEDIA or type(title) is not str or not 1 <= len(title) <= 80
            or type(body) is not str or len(body) > 100000 or format not in ('plain-text', 'markdown')):
        raise ValueError('Invalid working document export')
    destination = BytesIO()
    content_blocks = blocks(body, format)
    titled = bool(format == 'markdown' and content_blocks and content_blocks[0].heading == 1 and content_blocks[0].text == title)
    if output == 'docx':
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt, Inches
        document = Document()
        document.core_properties.title = title
        document.core_properties.author = 'ClassMatter'
        for name in ('Normal', 'Title', 'Quote', *(f'Heading {level}' for level in range(1, 7))):
            style = document.styles[name]
            style.font.name = 'Microsoft YaHei'
            fonts = style.element.get_or_add_rPr().rFonts
            if fonts is None:
                fonts = OxmlElement('w:rFonts'); style.element.get_or_add_rPr().append(fonts)
            fonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
            # Word gives theme attributes precedence over explicit family names.
            # Remove template font-theme references on the styles we export.
            for attribute in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
                fonts.attrib.pop(qn('w:' + attribute), None)
        document.styles['Normal'].font.size = Pt(11)
        if not titled:
            document.add_heading(title, level=0)
        for index, block in enumerate(content_blocks):
            paragraph = document.add_heading('', level=0 if titled and index == 0 else block.heading) if block.heading else document.add_paragraph()
            if block.quoted and not block.heading:
                paragraph.style = document.styles['Quote']
            if block.depth:
                paragraph.paragraph_format.left_indent = Inches(.25 * block.depth)
                paragraph.paragraph_format.first_line_indent = Inches(-.15)
            for span in block.runs:
                run = paragraph.add_run(span.text)
                run.bold, run.italic = True if span.bold else None, True if span.italic else None
                if span.code:
                    run.font.name = 'Consolas'
        document.save(destination)
    else:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        # Bounded pagination preserves text instead of cropping or silently
        # discarding paragraphs. No external font, image or URL is fetched.
        pages, lines, heading = [], [], title
        def flush():
            if lines:
                pages.append((heading, tuple(lines))); lines.clear()
                if len(pages) >= MAX_SLIDES:
                    raise ArtifactTooLarge()
        for block in content_blocks[1:] if titled else content_blocks:
            if block.heading and len(block.text) <= 32:
                flush(); heading = block.text
                # A heading-only section must not disappear on the next one.
                lines.append(())
                continue
            visible = Block((Run('› '),) + block.runs) if block.quoted else block
            for line in wrapped_runs(visible):
                if len(lines) == 10:
                    flush()
                lines.append(line)
        flush()
        if not body:
            pages.clear()
        presentation = Presentation()
        presentation.slide_width, presentation.slide_height = Inches(13.333), Inches(7.5)
        presentation.core_properties.title = title
        presentation.core_properties.author = 'ClassMatter'
        def text_box(slide, paragraphs, top, height, size, bold):
            frame = slide.shapes.add_textbox(Inches(.7), Inches(top), Inches(11.9), Inches(height)).text_frame
            frame.word_wrap = True
            for index, spans in enumerate(paragraphs):
                paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                paragraph.font.name, paragraph.font.size, paragraph.font.bold = 'Microsoft YaHei', Pt(size), bold
                paragraph.space_after = Pt(8)
                for span in spans:
                    run = paragraph.add_run(); run.text = span.text
                    run.font.bold, run.font.italic = True if span.bold else None, True if span.italic else None
                    if span.code:
                        run.font.name = 'Consolas'
            return frame
        cover = presentation.slides.add_slide(presentation.slide_layouts[6])
        from pptx.enum.text import PP_ALIGN
        cover_text = text_box(cover, [(Run(line),) for line in wrap(title, width=28, replace_whitespace=False, drop_whitespace=False)], 2, 3.5, 28, True)
        for paragraph in cover_text.paragraphs:
            paragraph.alignment = PP_ALIGN.CENTER
        for section, content in pages:
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            # Full title appears on the cover. Later headers can abbreviate.
            name = section if len(section) <= 32 else section[:32] + '…'
            text_box(slide, [(Run(name),)], .4, .8, 24, True)
            text_box(slide, content, 1.5, 5.5, 20, False)
        presentation.save(destination)
    content = destination.getvalue()
    if len(content) > MAX_BYTES:
        raise ArtifactTooLarge()
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).rstrip(' .') or 'ClassMatter'
    return OfficeArtifact(content, MEDIA[output], filename + '.' + output)
