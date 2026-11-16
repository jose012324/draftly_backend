"""WebSocket consumer: live updates and presence for a single document.

Written as a plain ASGI application (no consumer class) to stay consistent
with the function-based views of this project.

The ASGI interface is raw: the application receives ``(scope, receive, send)``
and answers with ASGI messages (``websocket.accept``, ``websocket.send``,
``websocket.close``). Channels 4 does not add any convenience methods to a
plain callable, so the small helpers below do that job.

Protocol
--------
connect   ``ws://<host>/ws/documents/<uuid>/?token=<api-token>``
receive   ``{"type": "ping"}``              -> ``{"type": "pong"}``
server    ``{"type": "hello", "version": N}`` on connect
server    ``{"type": "update", "content": …, "version": N, "author_id": …}``
server    ``{"type": "presence", "users": [{id, name}]}``

The token is checked on connect and the role is resolved with the same
permission helpers the REST API uses — a viewer can join, but only editors
and the owner may change anything (and changes are written through the REST
API, never through the socket).
"""

import asyncio
import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from rest_framework.authtoken.models import Token

from .models import Document
from .permissions import get_role

logger = logging.getLogger(__name__)

# group -> {channel_name: {'id': int, 'name': str}}
_PRESENCE = {}

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_INTERNAL_ERROR = 4500


# ---------------------------------------------------------------------------
# ASGI helpers
# ---------------------------------------------------------------------------


async def _send_json(send, payload):
    """Send a JSON message to the browser."""
    await send({'type': 'websocket.send', 'text': json.dumps(payload)})


async def _close(send, code):
    """Close the connection with an application specific code."""
    await send({'type': 'websocket.close', 'code': code})


# ---------------------------------------------------------------------------
# Database helpers (they must not run in the event loop thread)
# ---------------------------------------------------------------------------


def _token_from_scope(scope):
    """Read the API token from the query string."""
    query = scope.get('query_string') or b''
    values = parse_qs(query.decode('utf-8', errors='ignore'))
    tokens = values.get('token') or []
    return tokens[0] if tokens else ''


async def _authenticate(token):
    """Return the user of an API token (or None)."""

    def _lookup():
        try:
            return Token.objects.select_related('user').get(key=token).user
        except Token.DoesNotExist:
            return None

    return await database_sync_to_async(_lookup)()


async def _get_document(document_id):
    """The document with that id (or None)."""

    def _lookup():
        try:
            return Document.objects.select_related('owner').get(pk=document_id)
        except (Document.DoesNotExist, ValueError, TypeError):
            return None

    return await database_sync_to_async(_lookup)()


async def _role_for(document, user):
    """The role of the user on the document (owner / editor / viewer / None)."""

    def _lookup():
        return get_role(document, user)

    return await database_sync_to_async(_lookup)()


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


async def _broadcast_presence(group):
    """Tell everybody in the group who is currently connected."""
    layer = get_channel_layer()
    if layer is None:
        return

    unique = {}
    for entry in _PRESENCE.get(group, {}).values():
        unique[entry['id']] = entry

    await layer.group_send(group, {'type': 'presence', 'users': list(unique.values())})


def _to_client_message(event):
    """Translate a channel-layer event into a message for the browser."""
    kind = event.get('type')

    if kind == 'document.updated':
        return {
            'type': 'update',
            'document_id': event.get('document_id'),
            'content': event.get('content'),
            'title': event.get('title'),
            'version': event.get('version'),
            'author_id': event.get('author_id'),
            'author_name': event.get('author_name'),
        }

    if kind == 'presence':
        return {'type': 'presence', 'users': event.get('users', [])}

    if kind == 'collab':
        # The live stream of the editors (content and selection).
        return {
            'type': 'collab',
            'kind': event.get('kind'),
            'content': event.get('content'),
            'anchor': event.get('anchor'),
            'head': event.get('head'),
            'user_id': event.get('user_id'),
            'user_name': event.get('user_name'),
        }

    return None


# ---------------------------------------------------------------------------
# The consumer
# ---------------------------------------------------------------------------


async def document_consumer(scope, receive, send):
    """Subscribe to the live updates of one document."""
    try:
        await _subscribe(scope, receive, send)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception('Live connection failed (%s)', scope.get('path'))
        try:
            await _close(send, CLOSE_INTERNAL_ERROR)
        except Exception:
            pass


async def _subscribe(scope, receive, send):
    document_id = scope['url_route']['kwargs']['document_id']
    token = _token_from_scope(scope)

    user = await _authenticate(token)
    if user is None:
        logger.info('Live connection refused: invalid token')
        await _close(send, CLOSE_UNAUTHENTICATED)
        return

    document = await _get_document(document_id)
    if document is None:
        logger.info('Live connection refused: unknown document %s', document_id)
        await _close(send, CLOSE_NOT_FOUND)
        return

    role = await _role_for(document, user)
    if role is None:
        logger.info('Live connection refused: %s has no access', user.email)
        await _close(send, CLOSE_FORBIDDEN)
        return

    layer = get_channel_layer()
    if layer is None:
        logger.warning('Live connection refused: no channel layer configured')
        await _close(send, CLOSE_FORBIDDEN)
        return

    group = f'document.{document_id}'
    channel_name = await layer.new_channel()

    await layer.group_add(group, channel_name)
    _PRESENCE.setdefault(group, {})[channel_name] = {
        'id': user.id,
        'name': user.get_full_name() or user.username,
    }

    await send({'type': 'websocket.accept'})
    await _send_json(
        send,
        {
            'type': 'hello',
            'document_id': str(document.id),
            'version': document.version,
            'role': role,
            'user_id': user.id,
        },
    )
    await _broadcast_presence(group)

    main_task = asyncio.current_task()

    async def read_client():
        """Read the messages of the browser; detect disconnects."""
        try:
            while True:
                message = await receive()

                if message['type'] == 'websocket.disconnect':
                    break

                text = message.get('text')
                if not text:
                    continue

                try:
                    data = json.loads(text)
                except ValueError:
                    continue

                message_type = data.get('type')

                if message_type == 'collab':
                    # Live editing data (content, selection) is relayed to the
                    # group as it is — it never touches the database.
                    payload = dict(data)
                    payload['type'] = 'collab'
                    payload['user_id'] = user.id
                    payload['user_name'] = user.get_full_name() or user.username
                    await layer.group_send(group, payload)

                elif message_type == 'ping':
                    await _send_json(send, {'type': 'pong', 'version': document.version})
        except Exception:
            pass
        finally:
            if main_task is not None:
                main_task.cancel()

    reader = asyncio.create_task(read_client())

    try:
        while True:
            event = await layer.receive(channel_name)
            payload = _to_client_message(event)
            if payload:
                await _send_json(send, payload)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception('Live connection failed while reading events')
    finally:
        reader.cancel()
        _PRESENCE.get(group, {}).pop(channel_name, None)
        await layer.group_discard(group, channel_name)
        await _broadcast_presence(group)
