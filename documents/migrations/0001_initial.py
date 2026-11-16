import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import documents.tiptap


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Document',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('title', models.CharField(default='Untitled document', max_length=255)),
                ('content', models.JSONField(default=documents.tiptap.empty_document)),
                ('source_filename', models.CharField(blank=True, default='', max_length=255)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'owner',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='documents',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='DocumentPermission',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                (
                    'role',
                    models.CharField(
                        choices=[('viewer', 'Viewer'), ('editor', 'Editor')],
                        default='viewer',
                        max_length=10,
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'document',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='permissions',
                        to='documents.document',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='document_permissions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['created_at'],
                'unique_together': {('document', 'user')},
            },
        ),
    ]
