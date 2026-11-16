"""Create the demo accounts (and a few sample documents) for reviewers.

Usage:
    python manage.py seed_demo_users
    python manage.py seed_demo_users --password "another-secret"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from documents.models import Document, DocumentPermission
from documents.tiptap import heading, paragraph

User = get_user_model()

DEFAULT_PASSWORD = 'draftly123'

DEMO_USERS = [
    {
        'username': 'alice',
        'first_name': 'Alice',
        'last_name': 'Anderson',
        'email': 'alice@draftly.demo',
    },
    {
        'username': 'bob',
        'first_name': 'Bob',
        'last_name': 'Brown',
        'email': 'bob@draftly.demo',
    },
]


class Command(BaseCommand):
    help = 'Creates the demo users alice@draftly.demo and bob@draftly.demo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=DEFAULT_PASSWORD,
            help='Password given to both demo accounts (default: draftly123).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options['password']

        users = {}
        for data in DEMO_USERS:
            users[data['username']] = self._create_user(data, password)

        alice = users['alice']
        bob = users['bob']

        self._create_sample_documents(alice, bob)

        self.stdout.write(self.style.SUCCESS('\nDemo accounts are ready:'))
        self.stdout.write(f'  alice@draftly.demo  (owner)      password: {password}')
        self.stdout.write(f'  bob@draftly.demo    (collaborator) password: {password}\n')

    def _create_user(self, data, password):
        user, created = User.objects.get_or_create(
            username=data['username'],
            defaults={
                'first_name': data['first_name'],
                'last_name': data['last_name'],
                'email': data['email'],
            },
        )

        # Keep the demo data in sync when the command is re-run.
        user.first_name = data['first_name']
        user.last_name = data['last_name']
        user.email = data['email']
        user.is_active = True
        user.set_password(password)
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'{"Created" if created else "Updated"} {data["email"]} ({data["username"]})'
            )
        )
        return user

    def _create_sample_documents(self, alice, bob):
        proposal, _created = Document.objects.get_or_create(
            owner=alice,
            title='Project Proposal',
            defaults={
                'content': {
                    'type': 'doc',
                    'content': [
                        heading('Project Proposal', 1),
                        paragraph(
                            'Draftly keeps writing, organising and sharing in one workspace. '
                            'This document is shared with Bob so he can help editing it.'
                        ),
                        heading('Goals', 2),
                        {
                            'type': 'bulletList',
                            'content': [
                                {
                                    'type': 'listItem',
                                    'content': [
                                        paragraph('Import .txt, .md and .docx files as editable documents.')
                                    ],
                                },
                                {
                                    'type': 'listItem',
                                    'content': [paragraph('Share documents with viewer or editor roles.')],
                                },
                            ],
                        },
                    ],
                }
            },
        )

        DocumentPermission.objects.get_or_create(
            document=proposal,
            user=bob,
            defaults={'role': DocumentPermission.Role.EDITOR},
        )

        notes, _created = Document.objects.get_or_create(
            owner=alice,
            title='Meeting Notes',
            defaults={
                'content': {
                    'type': 'doc',
                    'content': [
                        heading('Meeting Notes', 1),
                        paragraph('Notes from the product review session.'),
                    ],
                }
            },
        )

        DocumentPermission.objects.get_or_create(
            document=notes,
            user=bob,
            defaults={'role': DocumentPermission.Role.VIEWER},
        )

        bob_document, _created = Document.objects.get_or_create(
            owner=bob,
            title="Bob's Checklist",
            defaults={
                'content': {
                    'type': 'doc',
                    'content': [
                        heading("Bob's Checklist", 1),
                        paragraph('Shared with Alice so she can follow the progress.'),
                    ],
                }
            },
        )

        DocumentPermission.objects.get_or_create(
            document=bob_document,
            user=alice,
            defaults={'role': DocumentPermission.Role.VIEWER},
        )
