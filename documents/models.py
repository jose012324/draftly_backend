"""Database models for documents and their permissions."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .tiptap import empty_document


class Document(models.Model):
    """A document owned by a user and optionally shared with other users."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default='Untitled document')

    # TipTap JSON document (headings, paragraphs, lists, formatting …).
    content = models.JSONField(default=empty_document)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents',
    )

    # Set when the document was created from an imported file.
    source_filename = models.CharField(max_length=255, blank=True, default='')

    # The document as a real .docx file (regenerated on every save).
    file = models.FileField(upload_to='documents/%Y/%m/', blank=True, null=True)

    # The original upload of an imported document (kept as it was uploaded).
    source_file = models.FileField(upload_to='imports/%Y/%m/', blank=True, null=True)

    # Incremented on every save — used to detect changes made by someone else.
    version = models.PositiveIntegerField(default=1)

    # Soft delete: deleted documents stay in the trash until purged.
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

    def soft_delete(self):
        """Move the document to the trash."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def restore(self):
        """Bring the document back from the trash."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])


class DocumentPermission(models.Model):
    """Grants a user access to a document (viewer or editor)."""

    class Role(models.TextChoices):
        VIEWER = 'viewer', 'Viewer'
        EDITOR = 'editor', 'Editor'

    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='permissions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='document_permissions',
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('document', 'user')
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user.email} -> {self.document.title} ({self.role})'
