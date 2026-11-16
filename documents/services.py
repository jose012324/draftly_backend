"""Business logic for documents.

The views stay thin: they resolve the request, call a service function and turn
the result into a response.

* `permissions.py` answers *who may do what*.
* `services.py`  describes *what happens*.
"""

import io

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils.text import slugify

from .docx_export import to_docx
from .models import Document, DocumentPermission
from .permissions import can_edit, get_role, is_owner
from .tiptap import empty_document

User = get_user_model()

VALID_ROLES = (DocumentPermission.Role.VIEWER, DocumentPermission.Role.EDITOR)

#: Maximum size of the TipTap JSON of a single document (2 MB).
MAX_CONTENT_BYTES = 2 * 1024 * 1024


class ServiceError(Exception):
    """Raised when a business rule is violated.

    The view turns it into a JSON response with ``status_code``.
    """

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def accessible_documents(user):
    """Documents the user owns or that were shared with them (trash excluded)."""
    return (
        Document.objects.filter(Q(owner=user) | Q(permissions__user=user))
        .exclude(is_deleted=True)
        .distinct()
    )


def trashed_documents(user):
    """Documents the user owns that are currently in the trash."""
    return Document.objects.filter(owner=user, is_deleted=True)


def list_documents(user, scope='all', search=''):
    """The documents of a scope: all, mine, shared, recent or trash."""
    scope = (scope or 'all').lower()

    if scope == 'trash':
        documents = trashed_documents(user)
    else:
        documents = accessible_documents(user)
        if scope == 'mine':
            documents = documents.filter(owner=user)
        elif scope == 'shared':
            documents = documents.exclude(owner=user)

    search = (search or '').strip()
    if search:
        documents = documents.filter(title__icontains=search)

    return documents


def get_document_for(user, document_id):
    """The document with that id — but only if the user may see it."""
    document = Document.objects.filter(pk=document_id).first()
    if document is None or get_role(document, user) is None:
        raise ServiceError('Document not found.', status_code=404)
    return document


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def validate_content_size(content):
    """Make sure a document does not grow beyond the allowed size."""
    if content is None:
        return
    if len(str(content).encode('utf-8')) > MAX_CONTENT_BYTES:
        raise ServiceError('This document is too large to save (limit 2 MB).')


def store_docx(document):
    """Write the document to disk as a .docx file.

    Every document exists twice: as TipTap JSON in the database and as a real
    Word file next to it. The file is what the download endpoint serves.
    """
    try:
        payload = to_docx(document.content, title=document.title)
    except Exception:
        # A broken export must never break the save itself.
        return False

    filename = f'{slugify(document.title) or "document"}.docx'
    document.file.save(filename, ContentFile(payload), save=False)
    document.save(update_fields=['file'])
    return True


def create_document(user, title=None, content=None, source_filename=''):
    """Create a new document owned by ``user``."""
    validate_content_size(content)

    document = Document.objects.create(
        owner=user,
        title=(title or 'Untitled document').strip()[:255] or 'Untitled document',
        content=content or empty_document(),
        source_filename=source_filename,
    )

    store_docx(document)
    return document


def update_document(document, user, title=None, content=None):
    """Update the title and/or the content of a document."""
    if not can_edit(document, user):
        raise ServiceError(
            'You do not have permission to edit this document.',
            status_code=403,
        )

    validate_content_size(content)

    if title is not None:
        document.title = title.strip()[:255] or 'Untitled document'
    if content is not None:
        document.content = content

    # The version tells the other editors that something changed.
    document.version = (document.version or 0) + 1
    document.save(update_fields=['title', 'content', 'updated_at', 'version'])

    # Keep the .docx file on disk in sync with the content.
    store_docx(document)

    return document


def soft_delete_document(document, user):
    """Move a document to the trash."""
    if not is_owner(document, user):
        raise ServiceError('Only the owner can delete this document.', status_code=403)

    document.soft_delete()
    return document


def restore_document(document, user):
    """Bring a document back from the trash."""
    if not is_owner(document, user):
        raise ServiceError('Only the owner can restore this document.', status_code=403)

    document.restore()
    return document


def purge_document(document, user):
    """Delete a document permanently."""
    if not is_owner(document, user):
        raise ServiceError('Only the owner can delete this document.', status_code=403)

    document.delete()


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------


def list_permissions(document):
    """Everyone that was given access to the document."""
    return document.permissions.select_related('user')


def share_document(document, user, email, role=DocumentPermission.Role.VIEWER):
    """Grant access to the document (owner only)."""
    if not is_owner(document, user):
        raise ServiceError('Only the owner can share this document.', status_code=403)

    email = (email or '').strip()
    role = role or DocumentPermission.Role.VIEWER

    if not email:
        raise ServiceError('An e-mail address is required.')

    if role not in VALID_ROLES:
        raise ServiceError('Role must be either "viewer" or "editor".')

    target = User.objects.filter(email__iexact=email).first()
    if target is None:
        raise ServiceError('No user with that e-mail address.', status_code=404)

    if target.id == document.owner_id:
        raise ServiceError('The owner already has full access to this document.')

    permission, created = DocumentPermission.objects.get_or_create(
        document=document,
        user=target,
        defaults={'role': role},
    )

    if not created and permission.role != role:
        permission.role = role
        permission.save(update_fields=['role'])

    return permission, created


def change_permission(document, user, permission_id, role):
    """Change the role of an existing permission (owner only)."""
    if not is_owner(document, user):
        raise ServiceError('Only the owner can manage the sharing list.', status_code=403)

    if role not in VALID_ROLES:
        raise ServiceError('Role must be either "viewer" or "editor".')

    permission = DocumentPermission.objects.filter(id=permission_id, document=document).first()
    if permission is None:
        raise ServiceError('Permission not found.', status_code=404)

    permission.role = role
    permission.save(update_fields=['role'])
    return permission


def revoke_permission(document, user, user_id):
    """Remove the access of a user (owner only)."""
    if not is_owner(document, user):
        raise ServiceError('Only the owner can manage the sharing list.', status_code=403)

    permission = DocumentPermission.objects.filter(document=document, user_id=user_id).first()
    if permission is None:
        raise ServiceError('Permission not found.', status_code=404)

    permission.delete()
    return permission
