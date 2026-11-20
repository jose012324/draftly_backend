"""Tests for the live updates (WebSocket) and the version tracking."""

import uuid

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from django.test import TransactionTestCase

from draftly_backend.asgi import application

from .models import Document

User = get_user_model()

SAMPLE_CONTENT = {
    'type': 'doc',
    'content': [
        {
            'type': 'paragraph',
            'content': [{'type': 'text', 'text': 'Hello Draftly.'}],
        }
    ],
}


class DocumentSocketTests(TransactionTestCase):
    """The socket may only be opened by users who have access to the document."""

    def setUp(self):
        self.owner = User.objects.create_user('alice', 'alice@draftly.demo', 'draftly123')
        self.editor = User.objects.create_user('bob', 'bob@draftly.demo', 'draftly123')
        self.outsider = User.objects.create_user('dave', 'dave@draftly.demo', 'draftly123')

        self.document = Document.objects.create(
            owner=self.owner,
            title='Shared document',
            content=SAMPLE_CONTENT,
        )

        self.owner_token = Token.objects.create(user=self.owner).key
        self.editor_token = Token.objects.create(user=self.editor).key
        self.outsider_token = Token.objects.create(user=self.outsider).key

    def _url(self, token, document=None):
        document = document or self.document
        return f'/ws/documents/{document.id}/?token={token}'

    async def _connect(self, token, document=None):
        communicator = WebsocketCommunicator(application, self._url(token, document))
        connected, _subprotocol = await communicator.connect()
        return communicator, connected

    async def test_owner_receives_hello(self):
        communicator, connected = await self._connect(self.owner_token)

        self.assertTrue(connected)
        message = await communicator.receive_json_from()

        self.assertEqual(message['type'], 'hello')
        self.assertEqual(message['role'], 'owner')
        self.assertEqual(message['version'], self.document.version)

        await communicator.disconnect()

    async def test_unknown_token_is_rejected(self):
        communicator, connected = await self._connect('not-a-real-token')

        self.assertFalse(connected)

    async def test_user_without_access_is_rejected(self):
        communicator, connected = await self._connect(self.outsider_token)

        self.assertFalse(connected)

    async def test_unknown_document_is_rejected(self):
        missing = uuid.uuid4()
        communicator = WebsocketCommunicator(
            application,
            f'/ws/documents/{missing}/?token={self.owner_token}',
        )
        connected, _subprotocol = await communicator.connect()

        self.assertFalse(connected)
