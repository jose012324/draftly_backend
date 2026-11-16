"""Serializers that turn documents and permissions into JSON."""

from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Document, DocumentPermission
from .permissions import get_role
from .tiptap import build_snippet, count_words


class DocumentListSerializer(serializers.ModelSerializer):
    """Compact representation used in the document lists."""

    owner = UserSerializer(read_only=True)
    role = serializers.SerializerMethodField()
    snippet = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            'id',
            'title',
            'snippet',
            'word_count',
            'owner',
            'role',
            'version',
            'created_at',
            'updated_at',
            'is_deleted',
            'source_filename',
        ]
        read_only_fields = fields

    def get_role(self, obj):
        """The role of the requesting user on this document."""
        request = self.context.get('request')
        if request is None:
            return None

        return get_role(obj, request.user)

    def get_snippet(self, obj):
        return build_snippet(obj.content)

    def get_word_count(self, obj):
        return count_words(obj.content)


class DocumentDetailSerializer(DocumentListSerializer):
    """Full representation including the content and the sharing list."""

    content = serializers.JSONField()
    shares = serializers.SerializerMethodField()

    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + ['content', 'shares']
        read_only_fields = fields

    def get_shares(self, obj):
        permissions = obj.permissions.select_related('user')
        return ShareSerializer(permissions, many=True).data


class DocumentCreateSerializer(serializers.ModelSerializer):
    """Payload used when a new document is created."""

    content = serializers.JSONField(required=False)

    class Meta:
        model = Document
        fields = ['title', 'content']

    def create(self, validated_data):
        validated_data.setdefault('title', 'Untitled document')
        return Document.objects.create(**validated_data)


class DocumentUpdateSerializer(serializers.ModelSerializer):
    """Payload used when a document is edited (title and/or content)."""

    content = serializers.JSONField(required=False)

    class Meta:
        model = Document
        fields = ['title', 'content']


class ShareSerializer(serializers.ModelSerializer):
    """A single sharing entry."""

    user = UserSerializer(read_only=True)

    class Meta:
        model = DocumentPermission
        fields = ['id', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
