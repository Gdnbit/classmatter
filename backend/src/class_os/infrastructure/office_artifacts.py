"""Replaceable text-only Office renderer. No model, network or business writes."""
from io import BytesIO
import re
from textwrap import wrap
from class_os.application.document_artifacts import ExportFormat, MEDIA, MAX_BYTES, ArtifactTooLarge, OfficeArtifact

MAX_SLIDES = 150


def blocks(body, format):
    for line in body.split('\n'):
        heading = re.fullmatch(r'(#{1,6})[ \t]+(.+)', line) if format == 'markdown' else None
        yield (len(heading[1]), heading[2]) if heading else (0, line)


def render_office(title: str, body: str, format: str, output: ExportFormat) -> OfficeArtifact:
    if (output not in MEDIA or type(title) is not str or not 1 <= len(title) <= 80
            or type(body) is not str or len(body) > 100000 or format not in ('plain-text', 'markdown')):
        raise ValueError('Invalid working document export')
    destination = BytesIO()
    if output == 'docx':
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt
        document = Document()
        document.core_properties.title = title
        document.core_properties.author = 'ClassMatter'
        style = document.styles['Normal']
        style.font.name, style.font.size = 'Microsoft YaHei', Pt(11)
        fonts = OxmlElement('w:rFonts'); fonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        style.element.get_or_add_rPr().append(fonts)
        document.add_heading(title, level=0)
        for level, value in blocks(body, format):
            if level:
                document.add_heading(value, level=level)
            else:
                document.add_paragraph(value)
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
        for level, value in blocks(body, format):
            if level and len(value) <= 32:
                flush(); heading = value
                # A heading-only section must not disappear on the next one.
                lines.append('')
                continue
            for line in wrap(value, width=32, expand_tabs=False, replace_whitespace=False,
                             drop_whitespace=False, break_on_hyphens=False) or ['']:
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
        def text_box(slide, text, top, height, size, bold):
            frame = slide.shapes.add_textbox(Inches(.7), Inches(top), Inches(11.9), Inches(height)).text_frame
            frame.word_wrap = True
            frame.text = text
            for paragraph in frame.paragraphs:
                paragraph.font.name, paragraph.font.size, paragraph.font.bold = 'Microsoft YaHei', Pt(size), bold
                paragraph.space_after = Pt(8)
            return frame
        cover = presentation.slides.add_slide(presentation.slide_layouts[6])
        from pptx.enum.text import PP_ALIGN
        cover_text = text_box(cover, '\n'.join(wrap(title, width=28, replace_whitespace=False, drop_whitespace=False)), 2, 3.5, 28, True)
        for paragraph in cover_text.paragraphs:
            paragraph.alignment = PP_ALIGN.CENTER
        for section, content in pages:
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            # Full title appears on the cover. Later headers can abbreviate.
            name = section if len(section) <= 32 else section[:32] + '…'
            text_box(slide, name, .4, .8, 24, True)
            text_box(slide, '\n'.join(content), 1.5, 5.5, 20, False)
        presentation.save(destination)
    content = destination.getvalue()
    if len(content) > MAX_BYTES:
        raise ArtifactTooLarge()
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).rstrip(' .') or 'ClassMatter'
    return OfficeArtifact(content, MEDIA[output], filename + '.' + output)
