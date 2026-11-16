"""Turn uploaded files (.txt, .md, .docx) into editable Draftly documents."""

from .tiptap import docx_to_document, markdown_to_document, text_to_document

ALLOWED_EXTENSIONS = {'txt', 'md', 'docx'}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


class UnsupportedFileError(Exception):
    """Raised when a file cannot be imported."""


def file_extension(filename):
    """The lower case extension of a file name (without the dot)."""
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


def title_from_filename(filename):
    """Turn "my-notes_final.docx" into "My Notes Final"."""
    base = file_extension(filename)
    name = filename[: -(len(base) + 1)] if base else filename
    words = name.replace('-', ' ').replace('_', ' ').split()
    return ' '.join(word.capitalize() for word in words) or 'Untitled document'


def _read_text(uploaded_file):
    uploaded_file.seek(0)
    return uploaded_file.read().decode('utf-8', errors='replace')


def import_uploaded_file(uploaded_file):
    """Return a ``(title, content)`` tuple for an uploaded file.

    The content is a TipTap JSON document, so the imported file becomes a
    fully editable Draftly document instead of a static attachment.
    """
    extension = file_extension(uploaded_file.name)

    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileError('Only .txt, .md and .docx files can be imported.')

    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise UnsupportedFileError('The file is larger than 5 MB.')

    if extension == 'txt':
        content = text_to_document(_read_text(uploaded_file))
    elif extension == 'md':
        content = markdown_to_document(_read_text(uploaded_file))
    else:
        uploaded_file.seek(0)
        content = docx_to_document(uploaded_file)

    title = title_from_filename(uploaded_file.name)

    # If the document starts with a heading, use that heading as the title.
    first_block = (content.get('content') or [{}])[0]
    if first_block.get('type') == 'heading':
        heading_text = ''.join(node.get('text', '') for node in first_block.get('content') or [])
        if heading_text.strip():
            title = heading_text.strip()[:255]

    return title, content
