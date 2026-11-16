"""TipTap -> .docx.

Every Draftly document is stored twice: as TipTap JSON in the database (the
editable source of truth) and as a real ``.docx`` file on disk (the file you
download, open in Word or send to somebody else).

An imported file keeps its original upload next to it, so "download original"
returns exactly the file that was uploaded.
"""

import io

from docx import Document as DocxFile
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

CODE_FONT = 'Consolas'
LINK_COLOR = RGBColor(0x20, 0x4A, 0x3A)


def to_docx(content, title=''):
    """Convert a TipTap document into the bytes of a ``.docx`` file."""
    document = DocxFile()

    if title:
        document.core_properties.title = title

    _add_blocks(document, (content or {}).get('content') or [])

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _add_blocks(document, blocks):
    for block in blocks or []:
        kind = block.get('type')

        if kind == 'heading':
            level = min(max((block.get('attrs') or {}).get('level', 1), 1), 9)
            paragraph = document.add_heading('', level=level)
            _add_inline(paragraph, block)

        elif kind == 'paragraph':
            paragraph = document.add_paragraph()
            _add_inline(paragraph, block)

        elif kind == 'blockquote':
            paragraph = _styled_paragraph(document, ('Quote', 'Intense Quote'))
            if paragraph is None:
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Pt(24)
            _add_inline(paragraph, block)

        elif kind == 'codeBlock':
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Pt(18)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)
            run = paragraph.add_run(_plain_text(block))
            run.font.name = CODE_FONT
            run.font.size = Pt(9.5)

        elif kind == 'horizontalRule':
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)
            run = paragraph.add_run('—' * 24)
            run.font.color.rgb = RGBColor(0xC8, 0xC6, 0xBE)

        elif kind in ('bulletList', 'orderedList'):
            style = 'List Bullet' if kind == 'bulletList' else 'List Number'
            for item in block.get('content') or []:
                _add_list_item(document, item, style)

        else:
            paragraph = document.add_paragraph()
            _add_inline(paragraph, block)


def _add_list_item(document, item, style):
    """A list item — the first paragraph becomes the item, the rest is nested."""
    blocks = item.get('content') or []

    for index, child in enumerate(blocks):
        if index == 0 and child.get('type') == 'paragraph':
            paragraph = _styled_paragraph(document, (style,))
            if paragraph is None:
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Pt(24)
            _add_inline(paragraph, child)
        else:
            _add_blocks(document, [child])


def _styled_paragraph(document, styles):
    """A paragraph with the first style that exists in the template."""
    for style in styles:
        try:
            return document.add_paragraph(style=style)
        except KeyError:
            continue
    return None


# ---------------------------------------------------------------------------
# Inline content
# ---------------------------------------------------------------------------


def _plain_text(block):
    parts = []
    for child in block.get('content') or []:
        if child.get('type') == 'text':
            parts.append(child.get('text', ''))
        else:
            parts.append(_plain_text(child))
    return ''.join(parts)


def _add_inline(paragraph, block):
    """Add the text of a block to a paragraph, marks included."""
    for child in block.get('content') or []:
        if child.get('type') == 'text':
            _add_run(paragraph, child)
        else:
            _add_inline(paragraph, child)


def _add_run(paragraph, node):
    text = node.get('text', '')
    if not text:
        return

    marks = node.get('marks') or []
    link = next((mark for mark in marks if mark.get('type') == 'link'), None)

    if link is not None:
        url = (link.get('attrs') or {}).get('href', '')
        _add_hyperlink(paragraph, url, text)
        return

    run = paragraph.add_run(text)

    for mark in marks:
        kind = mark.get('type')
        if kind == 'bold':
            run.bold = True
        elif kind == 'italic':
            run.italic = True
        elif kind == 'underline':
            run.underline = True
        elif kind == 'strike':
            run.font.strike = True
        elif kind == 'code':
            run.font.name = CODE_FONT
            run.font.size = Pt(10)


def _add_hyperlink(paragraph, url, text):
    """A real Word hyperlink (python-docx has no helper for it)."""
    if not url:
        paragraph.add_run(text)
        return

    part = paragraph.part
    relationship_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), relationship_id)

    run = OxmlElement('w:r')
    properties = OxmlElement('w:rPr')

    color = OxmlElement('w:color')
    color.set(qn('w:val'), '204A3A')
    properties.append(color)

    underline = OxmlElement('w:u')
    underline.set(qn('w:val'), 'single')
    properties.append(underline)

    run.append(properties)

    text_element = OxmlElement('w:t')
    text_element.text = text
    run.append(text_element)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)
