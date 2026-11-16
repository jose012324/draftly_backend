"""WebSocket routes of the Draftly API."""

from django.urls import path

from documents.consumers import document_consumer

websocket_urlpatterns = [
    path('ws/documents/<uuid:document_id>/', document_consumer, name='ws-document'),
]
