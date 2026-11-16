"""Exporters — the other direction: TipTap JSON -> Markdown / HTML / text.

The importer turns files into documents; this module turns a document back
into a file. It lives next to `tiptap.py` so both directions of the
conversion stay in one place.
"""

_HTML_ESCAPES = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}


def escape_html(text):
    """Escape the characters that would break an HTML document."""
    return ''.join(_HTML_ESCAPES.get(char, char) for char in text)


# ---------------------------------------------------------------------------
# Inline content
# ---------------------------------------------------------------------------


def _inline_markdown(node):
    """A text node with its marks as Markdown."""
    text = node.get('text', '')
    if not text:
        return ''

    for mark in node.get('marks') or []:
        kind = mark.get('type')
        attrs = mark.get('attrs') or {}

        if kind == 'bold':
            text = f'**{text}**'
        elif kind == 'italic':
            text = f'*{text}*'
        elif kind == 'strike':
            text = f'~~{text}~~'
        elif kind == 'code':
            text = f'`{text}`'
        elif kind == 'link':
            text = f'[{text}]({attrs.get("href", "")})'

    return text


def _inline_html(node):
    """A text node with its marks as HTML."""
    text = escape_html(node.get('text', ''))
    if not text:
        return ''

    for mark in node.get('marks') or []:
        kind = mark.get('type')
        attrs = mark.get('attrs') or {}

        if kind == 'bold':
            text = f'<strong>{text}</strong>'
        elif kind == 'italic':
            text = f'<em>{text}</em>'
        elif kind == 'strike':
            text = f'<s>{text}</s>'
        elif kind == 'code':
            text = f'<code>{text}</code>'
        elif kind == 'link':
            href = escape_html(attrs.get('href', ''))
            text = f'<a href="{href}">{text}</a>'

    return text


def _inline_text(node):
    """The plain text of a block (all inline nodes joined)."""
    parts = []
    for child in node.get('content') or []:
        if child.get('type') == 'text':
            parts.append(child.get('text', ''))
        else:
            parts.append(_inline_text(child))
    return ''.join(parts)


def _inline_markdown_text(block):
    """The inline content of a block as Markdown."""
    parts = []
    for child in block.get('content') or []:
        if child.get('type') == 'text':
            parts.append(_inline_markdown(child))
        else:
            parts.append(_inline_markdown_text(child))
    return ''.join(parts)


def _inline_html_text(block):
    """The inline content of a block as HTML."""
    parts = []
    for child in block.get('content') or []:
        if child.get('type') == 'text':
            parts.append(_inline_html(child))
        else:
            parts.append(_inline_html_text(child))
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _blocks_to_markdown(blocks, depth=0):
    """A list of TipTap blocks as Markdown."""
    lines = []

    for block in blocks or []:
        kind = block.get('type')
        indent = '  ' * depth

        if kind == 'heading':
            level = min(max((block.get('attrs') or {}).get('level', 1), 1), 6)
            lines.append(f"{indent}{'#' * level} {_inline_markdown_text(block)}")

        elif kind == 'paragraph':
            text = _inline_markdown_text(block)
            if text.strip():
                lines.append(f'{indent}{text}')

        elif kind == 'blockquote':
            text = _inline_markdown_text(block)
            lines.append('\n'.join(f'{indent}> {line}' for line in text.split('\n')))

        elif kind == 'codeBlock':
            code = _inline_text(block)
            lines.append(f'{indent}```\n{code}\n{indent}```')

        elif kind == 'horizontalRule':
            lines.append(f'{indent}---')

        elif kind in ('bulletList', 'orderedList'):
            index = 1
            for item in block.get('content') or []:
                marker = '-' if kind == 'bulletList' else f'{index}.'
                index += 1

                # The first paragraph of an item is its text, everything else
                # (nested lists, quotes) is rendered one level deeper.
                text = ''
                nested = []
                for position, child in enumerate(item.get('content') or []):
                    if position == 0 and child.get('type') == 'paragraph':
                        text = _inline_markdown_text(child)
                    else:
                        nested.append(child)

                lines.append(f'{indent}{marker} {text}'.rstrip())

                if nested:
                    lines.append(_blocks_to_markdown(nested, depth + 1))

        else:
            text = _inline_markdown_text(block)
            if text.strip():
                lines.append(f'{indent}{text}')

    return '\n'.join(lines)


def _blocks_to_html(blocks):
    """A list of TipTap blocks as HTML."""
    html = []

    for block in blocks or []:
        kind = block.get('type')

        if kind == 'heading':
            level = min(max((block.get('attrs') or {}).get('level', 1), 1), 6)
            html.append(f'<h{level}>{_inline_html_text(block)}</h{level}>')

        elif kind == 'paragraph':
            text = _inline_html_text(block)
            if text.strip():
                html.append(f'<p>{text}</p>')

        elif kind == 'blockquote':
            html.append(f'<blockquote>{_inline_html_text(block)}</blockquote>')

        elif kind == 'codeBlock':
            code = escape_html(_inline_text(block))
            html.append(f'<pre><code>{code}</code></pre>')

        elif kind == 'horizontalRule':
            html.append('<hr>')

        elif kind in ('bulletList', 'orderedList'):
            tag = 'ul' if kind == 'bulletList' else 'ol'
            items = []
            for item in block.get('content') or []:
                inner = ''.join(_blocks_to_html(item.get('content') or []))
                items.append(f'<li>{inner}</li>')
            html.append(f'<{tag}>{"".join(items)}</{tag}>')

        else:
            text = _inline_html_text(block)
            if text.strip():
                html.append(f'<p>{text}</p>')

    return html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def to_markdown(document):
    """A TipTap document as Markdown."""
    parts = []

    for block in (document or {}).get('content') or []:
        text = _blocks_to_markdown([block], 0)
        if text.strip():
            parts.append(text)

    return '\n\n'.join(parts) + '\n' if parts else ''


def to_html(document, title='Draftly document'):
    """A TipTap document as a standalone HTML page."""
    body = '\n'.join(_blocks_to_html((document or {}).get('content') or []))
    safe_title = escape_html(title)

    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'  <title>{safe_title}</title>\n'
        '  <style>\n'
        '    body{max-width:42rem;margin:4rem auto;padding:0 1.5rem;'
        'font:16px/1.7 Georgia,serif;color:#1b1b18}\n'
        '    h1,h2,h3{font-family:system-ui,sans-serif;letter-spacing:-.02em}\n'
        '    code{background:#f2f1ed;padding:.1em .35em;border-radius:4px}\n'
        '    blockquote{border-left:2px solid #d6336c;margin:1rem 0;'
        'padding-left:1rem;color:#6b6b63}\n'
        '  </style>\n'
        '</head>\n'
        '<body>\n'
        f'{body}\n'
        '</body>\n'
        '</html>\n'
    )
