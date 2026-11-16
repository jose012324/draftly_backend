"""Helpers for the TipTap JSON document format used by the Draftly editor.

The editor (TipTap) stores a document as a tree of nodes::

    {"type": "doc", "content": [{"type": "paragraph", "content": [...]}]}

The functions below create those nodes and read plain text back out of them,
which is what the document list (snippets) and the file importer need.
"""

import re

DOCUMENT_TYPE = 'doc'

_INLINE_PATTERN = re.compile(
    r'(\*\*.+?\*\*'          # **bold**
    r'|__.+?__'              # __bold__
    r'|\*[^*\n]+?\*'         # *italic*
    r'|`[^`\n]+?`'           # `code`
    r'|\[[^\]\n]+?\]\([^)\n]+?\))'  # [label](url)
)


def empty_document():
    """A brand new, empty document."""
    return {'type': DOCUMENT_TYPE, 'content': [{'type': 'paragraph'}]}


def text_node(text, marks=None):
    node = {'type': 'text', 'text': text}
    if marks:
        node['marks'] = marks
    return node


def paragraph(text=''):
    """A paragraph node, optionally with inline formatting."""
    if not text:
        return {'type': 'paragraph'}
    return {'type': 'paragraph', 'content': [text_node(text)]}


def heading(text, level=1):
    """A heading node (levels 1-3)."""
    level = min(max(int(level), 1), 3)
    return {
        'type': 'heading',
        'attrs': {'level': level},
        'content': [text_node(text)] if text else [],
    }


def blockquote(text):
    return {'type': 'blockquote', 'content': [paragraph(text)]}


def code_block(text):
    return {'type': 'codeBlock', 'content': [text_node(text)]}


def list_node(list_type, items):
    """A bullet or ordered list node."""
    return {
        'type': list_type,
        'content': [
            {'type': 'listItem', 'content': [paragraph(item)]}
            for item in items
        ],
    }


def inline_nodes(text):
    """Split a line into text nodes, supporting **bold**, *italic*, `code` and links."""
    nodes = []
    position = 0

    for match in _INLINE_PATTERN.finditer(text or ''):
        if match.start() > position:
            nodes.append(text_node(text[position:match.start()]))

        token = match.group(0)
        if token.startswith('**') and token.endswith('**'):
            nodes.append(text_node(token[2:-2], [{'type': 'bold'}]))
        elif token.startswith('__') and token.endswith('__'):
            nodes.append(text_node(token[2:-2], [{'type': 'bold'}]))
        elif token.startswith('`') and token.endswith('`'):
            nodes.append(text_node(token[1:-1], [{'type': 'code'}]))
        elif token.startswith('['):
            label, _, url = token.partition('](')
            nodes.append(
                text_node(label[1:], [{'type': 'link', 'attrs': {'href': url.rstrip(')')}}])
            )
        else:
            nodes.append(text_node(token[1:-1], [{'type': 'italic'}]))

        position = match.end()

    if position < len(text or ''):
        nodes.append(text_node(text[position:]))

    return nodes


def extract_text(node):
    """All plain text of a document (blocks are separated by newlines)."""
    if not isinstance(node, dict):
        return ''
    if node.get('type') == 'text':
        return node.get('text', '')

    parts = [extract_text(child) for child in node.get('content') or []]
    parts = [part for part in parts if part]

    node_type = node.get('type')

    if node_type == 'doc':
        # Top level: every block is a separate line.
        return '\n'.join(parts)
    if node_type in ('bulletList', 'orderedList'):
        return '\n'.join(parts)
    if node_type in ('paragraph', 'heading', 'blockquote', 'codeBlock', 'listItem'):
        # Inline content of a single block.
        return ''.join(parts)
    return ' '.join(parts)


def count_words(node):
    """Number of words in a document."""
    text = extract_text(node).strip()
    if not text:
        return 0
    return len(text.split())


def build_snippet(node, max_length=140):
    """A short, single line preview of a document."""
    text = ' '.join(extract_text(node).split())
    if not text:
        return ''
    if len(text) <= max_length:
        return text
    return f'{text[:max_length].rstrip()}…'


def text_to_document(text):
    """Convert plain text into a TipTap document (one paragraph per block)."""
    content = []

    for block in (text or '').split('\n\n'):
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        for line in lines:
            content.append(paragraph(line))

    if not content:
        content = [paragraph()]

    return {'type': DOCUMENT_TYPE, 'content': content}


def markdown_to_document(markdown):
    """Convert a (subset of) Markdown into a TipTap document."""
    content = []
    list_type = None
    list_items = []
    in_code_block = False
    code_lines = []

    def flush_list():
        nonlocal list_type, list_items
        if list_type and list_items:
            content.append(list_node(list_type, list_items))
        list_type = None
        list_items = []

    for raw_line in (markdown or '').split('\n'):
        line = raw_line.rstrip()
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith('```'):
            if in_code_block:
                content.append(code_block('\n'.join(code_lines)))
                code_lines = []
                in_code_block = False
            else:
                flush_list()
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(raw_line)
            continue

        if not stripped:
            flush_list()
            continue

        # Headings
        if stripped.startswith('#'):
            flush_list()
            level = len(stripped) - len(stripped.lstrip('#'))
            text = stripped.lstrip('#').strip()
            node = heading('', min(max(level, 1), 3))
            node['content'] = inline_nodes(text)
            content.append(node)
            continue

        # Blockquote
        if stripped.startswith('>'):
            flush_list()
            node = blockquote('')
            node['content'][0]['content'] = inline_nodes(stripped.lstrip('>').strip())
            content.append(node)
            continue

        # Lists
        bullet = re.match(r'^[-*+]\s+(.*)$', stripped)
        ordered = re.match(r'^\d+[.)]\s+(.*)$', stripped)
        if bullet or ordered:
            kind = 'bulletList' if bullet else 'orderedList'
            item_text = (bullet or ordered).group(1).strip()
            if list_type != kind:
                flush_list()
                list_type = kind
            list_items.append(item_text)
            continue

        # Plain paragraph
        flush_list()
        content.append({'type': 'paragraph', 'content': inline_nodes(stripped)})

    flush_list()

    if in_code_block and code_lines:
        content.append(code_block('\n'.join(code_lines)))

    if not content:
        content = [paragraph()]

    return {'type': DOCUMENT_TYPE, 'content': content}


def docx_to_document(file_object):
    """Convert a .docx file into a TipTap document."""
    try:
        from docx import Document as DocxFile
    except ImportError as error:  # pragma: no cover - dependency is declared
        raise RuntimeError('python-docx is required to import .docx files.') from error

    try:
        source = DocxFile(file_object)
    except Exception as error:
        raise ValueError('The .docx file could not be read.') from error

    content = []
    list_type = None
    list_items = []

    def flush_list():
        nonlocal list_type, list_items
        if list_type and list_items:
            content.append(list_node(list_type, list_items))
        list_type = None
        list_items = []

    for block in source.paragraphs:
        style = (block.style.name if block.style else '') or ''
        style = style.lower()
        text = block.text.strip()

        if not text:
            continue

        if style.startswith('heading 1'):
            flush_list()
            content.append(heading(text, 1))
        elif style.startswith('heading 2'):
            flush_list()
            content.append(heading(text, 2))
        elif style.startswith('heading 3'):
            flush_list()
            content.append(heading(text, 3))
        elif style in ('title', 'subtitle'):
            flush_list()
            content.append(heading(text, 1))
        elif style in ('quote', 'intense quote'):
            flush_list()
            content.append(blockquote(text))
        elif style in ('list bullet', 'list number', 'list paragraph'):
            kind = 'orderedList' if style == 'list number' else 'bulletList'
            if list_type != kind:
                flush_list()
                list_type = kind
            list_items.append(text)
        else:
            flush_list()
            content.append({'type': 'paragraph', 'content': inline_nodes(text)})

    flush_list()

    # Tables are converted into simple rows — the editor has no table extension.
    for table in source.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                content.append(paragraph(' | '.join(cells)))

    if not content:
        content = [paragraph()]

    return {'type': DOCUMENT_TYPE, 'content': content}
