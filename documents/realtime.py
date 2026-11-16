"""Channel-layer helpers.

The REST API stays the place where a document is written (it owns the
permission checks and the validation). After a successful save the new state is
fanned out to everybody who currently has the document open — that is the
"live" part, and it never bypasses the API rules.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def document_group(document_id):
    """The channel group of a document."""
    return f'document.{document_id}'


def broadcast_document_update(document, author):
    """Send the new state of a document to everyone who has it open.

    Returns ``True`` when the message was handed over to the channel layer.
    """
    layer = get_channel_layer()
    if layer is None:
        return False

    payload = {
        'type': 'document.updated',
        'document_id': str(document.id),
        'content': document.content,
        'title': document.title,
        'version': document.version,
        'author_id': author.id,
        'author_name': author.get_full_name() or author.username,
    }

    try:
        async_to_sync(layer.group_send)(document_group(document.id), payload)
    except Exception:
        # The realtime layer is a convenience — a failure must never break a save.
        return False

    return True
