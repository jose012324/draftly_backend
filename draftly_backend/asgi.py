"""
ASGI config for draftly_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.
Django is served over HTTP, the live document updates over WebSocket.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'draftly_backend.settings')

# The HTTP application has to be created after the settings are loaded.
django_asgi_app = get_asgi_application()

from draftly_backend.routing import websocket_urlpatterns  # noqa: E402


def _allowed_origins():
    """Origins that may open a WebSocket (the frontend plus the local hosts)."""
    from django.conf import settings

    origins = list(getattr(settings, 'CORS_ALLOWED_ORIGINS', []))
    for host in getattr(settings, 'ALLOWED_HOSTS', []):
        if host and host not in ('0.0.0.0', 'testserver'):
            origins.append(f'http://{host}')
            origins.append(f'https://{host}')
    return origins


def origin_guard(inner):
    """Reject WebSocket handshakes from unknown origins.

    Browsers always send an ``Origin`` header; clients without one (scripts,
    tests) are allowed through — the token and the role check still apply.
    """

    async def middleware(scope, receive, send):
        headers = dict(scope.get('headers') or [])
        origin = headers.get(b'origin', b'').decode('utf-8', errors='ignore')

        if origin and origin not in _allowed_origins():
            await send({'type': 'websocket.close', 'code': 4403})
            return

        return await inner(scope, receive, send)

    return middleware


application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        # The WebSocket application is a plain ASGI function — it creates its
        # own channel name through the channel layer.
        'websocket': origin_guard(URLRouter(websocket_urlpatterns)),
    }
)
