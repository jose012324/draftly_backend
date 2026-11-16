"""Admin registration for the document models."""

from django.contrib import admin

from .models import Document, DocumentPermission


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'is_deleted', 'created_at', 'updated_at')
    list_filter = ('is_deleted', 'created_at')
    search_fields = ('title', 'owner__email')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(DocumentPermission)
class DocumentPermissionAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('document__title', 'user__email')
