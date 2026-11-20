"""API tests for the documents endpoints.

The permission tests are the interesting ones: they prove that the access
rules are enforced by the backend and not just hidden in the frontend.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Document, DocumentPermission
from .services import store_docx

User = get_user_model()

SAMPLE_CONTENT = {
    'type': 'doc',
    'content': [
        {
            'type': 'heading',
            'attrs': {'level': 1},
            'content': [{'type': 'text', 'text': 'Project Proposal'}],
        },
        {
            'type': 'paragraph',
            'content': [{'type': 'text', 'text': 'Hello Draftly.'}],
        },
    ],
}


class DocumentApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user('alice', 'alice@draftly.demo', 'draftly123')
        self.editor = User.objects.create_user('bob', 'bob@draftly.demo', 'draftly123')
        self.viewer = User.objects.create_user('carol', 'carol@draftly.demo', 'draftly123')
        self.outsider = User.objects.create_user('dave', 'dave@draftly.demo', 'draftly123')

        self.document = Document.objects.create(
            owner=self.owner,
            title='Project Proposal',
            content=SAMPLE_CONTENT,
        )
        # Every document is stored as a .docx file as well.
        store_docx(self.document)

        DocumentPermission.objects.create(
            document=self.document,
            user=self.editor,
            role=DocumentPermission.Role.EDITOR,
        )
        DocumentPermission.objects.create(
            document=self.document,
            user=self.viewer,
            role=DocumentPermission.Role.VIEWER,
        )

    def detail_url(self, document=None):
        document = document or self.document
        return reverse('document-detail', args=[document.id])

    # ------------------------------------------------------------------
    # Creating and updating
    # ------------------------------------------------------------------

    def test_owner_can_create_document(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse('document-list'),
            {'title': 'Sprint plan', 'content': SAMPLE_CONTENT},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Sprint plan')
        self.assertEqual(response.data['owner']['email'], 'alice@draftly.demo')
        self.assertEqual(response.data['role'], 'owner')

    def test_owner_can_update_document(self):
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            self.detail_url(),
            {'title': 'Project Proposal v2'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Project Proposal v2')

    def test_shared_editor_can_update_document(self):
        self.client.force_authenticate(self.editor)

        response = self.client.patch(
            self.detail_url(),
            {'content': SAMPLE_CONTENT},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content']['content'][0]['type'], 'heading')

    def test_shared_viewer_cannot_update_document(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.patch(
            self.detail_url(),
            {'title': 'Hijacked'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.document.refresh_from_db()
        self.assertEqual(self.document.title, 'Project Proposal')

    def test_unauthenticated_user_cannot_access_document(self):
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_outsider_cannot_access_private_document(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewer_can_read_document(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'viewer')

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def test_content_persists_after_retrieval(self):
        self.client.force_authenticate(self.owner)

        self.client.patch(
            self.detail_url(),
            {'content': SAMPLE_CONTENT},
            format='json',
        )
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], SAMPLE_CONTENT)

        self.document.refresh_from_db()
        self.assertEqual(self.document.content, SAMPLE_CONTENT)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def test_list_contains_owned_and_shared_documents(self):
        self.client.force_authenticate(self.editor)

        response = self.client.get(reverse('document-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['role'], 'editor')

    def test_scope_shared_only_returns_documents_of_other_people(self):
        self.client.force_authenticate(self.owner)

        shared_document = Document.objects.create(
            owner=self.editor,
            title='Bob notes',
            content=SAMPLE_CONTENT,
        )
        DocumentPermission.objects.create(
            document=shared_document,
            user=self.owner,
            role=DocumentPermission.Role.VIEWER,
        )

        response = self.client.get(reverse('document-list'), {'scope': 'shared'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [str(shared_document.id)])

    def test_search_filters_by_title(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse('document-list'), {'search': 'proposal'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    # ------------------------------------------------------------------
    # Trash
    # ------------------------------------------------------------------

    def test_delete_moves_document_to_trash_and_restores_it(self):
        self.client.force_authenticate(self.owner)

        response = self.client.delete(self.detail_url())
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.document.refresh_from_db()
        self.assertTrue(self.document.is_deleted)

        trash = self.client.get(reverse('document-list'), {'scope': 'trash'})
        self.assertEqual(len(trash.data), 1)

        restore = self.client.post(reverse('document-restore', args=[self.document.id]))
        self.assertEqual(restore.status_code, status.HTTP_200_OK)

        self.document.refresh_from_db()
        self.assertFalse(self.document.is_deleted)

    def test_only_owner_can_delete_document(self):
        self.client.force_authenticate(self.editor)

        response = self.client.delete(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.document.refresh_from_db()
        self.assertFalse(self.document.is_deleted)

    # ------------------------------------------------------------------
    # Sharing
    # ------------------------------------------------------------------

    def test_owner_can_share_document_with_another_user(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse('document-share', args=[self.document.id]),
            {'email': 'dave@draftly.demo', 'role': 'viewer'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['email'], 'dave@draftly.demo')
        self.assertEqual(response.data['role'], 'viewer')

    def test_sharing_with_unknown_email_fails(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse('document-share', args=[self.document.id]),
            {'email': 'nobody@draftly.demo', 'role': 'viewer'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_sharing_with_an_invalid_role_fails(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse('document-share', args=[self.document.id]),
            {'email': 'dave@draftly.demo', 'role': 'admin'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editor_cannot_share_document(self):
        self.client.force_authenticate(self.editor)

        response = self.client.post(
            reverse('document-share', args=[self.document.id]),
            {'email': 'dave@draftly.demo', 'role': 'editor'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_permissions_endpoint_lists_every_collaborator(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse('document-permissions', args=[self.document.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(
            {item['user']['email'] for item in response.data},
            {'bob@draftly.demo', 'carol@draftly.demo'},
        )

    def test_owner_can_change_role_and_revoke_access(self):
        self.client.force_authenticate(self.owner)
        permission = DocumentPermission.objects.get(document=self.document, user=self.viewer)

        response = self.client.patch(
            reverse('document-permission-detail', args=[self.document.id, permission.id]),
            {'role': 'editor'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'editor')

        response = self.client.delete(
            reverse('document-share-revoke', args=[self.document.id, self.viewer.id])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            DocumentPermission.objects.filter(id=permission.id).exists()
        )

    def test_revoke_access_removes_read_access(self):
        self.client.force_authenticate(self.owner)

        self.client.delete(
            reverse('document-share-revoke', args=[self.document.id, self.viewer.id])
        )

        self.client.force_authenticate(self.viewer)
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # Importing
    # ------------------------------------------------------------------

    def test_import_txt_creates_editable_document(self):
        self.client.force_authenticate(self.owner)
        uploaded = SimpleUploadedFile(
            'meeting notes.txt',
            b'First line\n\nSecond line',
            content_type='text/plain',
        )

        response = self.client.post(reverse('document-import'), {'file': uploaded}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Meeting Notes')
        self.assertEqual(response.data['source_filename'], 'meeting notes.txt')
        self.assertEqual(len(response.data['content']['content']), 2)

    def test_import_rejects_unsupported_file_type(self):
        self.client.force_authenticate(self.owner)
        uploaded = SimpleUploadedFile('picture.png', b'binary', content_type='image/png')

        response = self.client.post(reverse('document-import'), {'file': uploaded}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Limits
    # ------------------------------------------------------------------

    def test_content_larger_than_the_limit_is_rejected(self):
        self.client.force_authenticate(self.owner)
        huge_content = {
            'type': 'doc',
            'content': [
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'x' * (2 * 1024 * 1024 + 100)}],
                }
            ],
        }

        response = self.client.patch(
            self.detail_url(),
            {'content': huge_content},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

    def test_owner_can_update_the_title_only(self):
        self.client.force_authenticate(self.owner)

        response = self.client.patch(self.detail_url(), {'title': 'Renamed'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Renamed')

    # ------------------------------------------------------------------
    # Version tracking (used to detect changes made by somebody else)
    # ------------------------------------------------------------------

    def test_version_increases_on_every_save(self):
        self.client.force_authenticate(self.owner)
        first_version = self.document.version

        response = self.client.patch(
            self.detail_url(),
            {'content': SAMPLE_CONTENT},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['version'], first_version)

    def test_version_endpoint_returns_the_current_version(self):
        self.client.force_authenticate(self.editor)

        response = self.client.get(reverse('document-version', args=[self.document.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['version'], self.document.version)

    def test_version_endpoint_is_hidden_from_users_without_access(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get(reverse('document-version', args=[self.document.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def test_owner_can_download_the_document_as_markdown(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(
            reverse('document-download', args=[self.document.id]),
            {'format': 'md'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(response['Content-Disposition'].endswith('.md"'))
        self.assertIn('Hello Draftly.', response.content.decode())

    def test_every_document_is_stored_as_a_docx_file(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse('document-list'),
            {'title': 'With a file', 'content': SAMPLE_CONTENT},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        document = Document.objects.get(id=response.data['id'])
        self.assertTrue(document.file, 'the document should have a .docx file')
        self.assertTrue(document.file.name.endswith('.docx'))

        # The file really is a Word document.
        with document.file.open('rb') as handle:
            self.assertEqual(handle.read(2), b'PK')

    def test_download_serves_the_stored_docx(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse('document-download', args=[self.document.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response['Content-Disposition'].endswith('.docx"'))
        self.assertEqual(b''.join(response.streaming_content)[:2], b'PK')

    def test_download_of_a_document_without_a_file_generates_one(self):
        self.client.force_authenticate(self.owner)
        self.document.file.delete(save=False)

        response = self.client.get(reverse('document-download', args=[self.document.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b''.join(response.streaming_content)[:2], b'PK')

    def test_import_keeps_the_original_upload(self):
        self.client.force_authenticate(self.owner)
        uploaded = SimpleUploadedFile(
            'notes.txt',
            b'First line\n\nSecond line',
            content_type='text/plain',
        )

        response = self.client.post(reverse('document-import'), {'file': uploaded}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        document = Document.objects.get(id=response.data['id'])
        self.assertTrue(document.source_file, 'the uploaded file should be kept')
        self.assertTrue(document.source_file.name.endswith('notes.txt'))

        download = self.client.get(
            reverse('document-download', args=[document.id]),
            {'format': 'original'},
        )
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertIn(b'First line', b''.join(download.streaming_content))

    def test_shared_editor_can_download_the_document(self):
        self.client.force_authenticate(self.editor)

        response = self.client.get(
            reverse('document-download', args=[self.document.id]),
            {'format': 'txt'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Hello Draftly.', response.content.decode())

    def test_download_as_json_returns_the_tiptap_document(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(
            reverse('document-download', args=[self.document.id]),
            {'format': 'json'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), SAMPLE_CONTENT)

    def test_user_without_access_cannot_download(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get(reverse('document-download', args=[self.document.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
