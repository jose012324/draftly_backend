"""Tests for the authentication endpoints."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AuthenticationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'alice',
            'alice@draftly.demo',
            'draftly123',
            first_name='Alice',
            last_name='Anderson',
        )

    def test_login_with_email_returns_token_and_user(self):
        response = self.client.post(
            reverse('login'),
            {'email': 'alice@draftly.demo', 'password': 'draftly123'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['email'], 'alice@draftly.demo')
        self.assertEqual(response.data['user']['full_name'], 'Alice Anderson')

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse('login'),
            {'email': 'alice@draftly.demo', 'password': 'wrong'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('token', response.data)

    def test_login_requires_email_and_password(self):
        response = self.client.post(reverse('login'), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_me_returns_the_signed_in_user(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'alice@draftly.demo')

    def test_me_requires_authentication(self):
        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalidates_the_token(self):
        login = self.client.post(
            reverse('login'),
            {'email': 'alice@draftly.demo', 'password': 'draftly123'},
            format='json',
        )
        token = login.data['token']

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        logout = self.client.post(reverse('logout'))
        self.assertEqual(logout.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(reverse('me'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_search_excludes_the_current_user(self):
        User.objects.create_user('bob', 'bob@draftly.demo', 'draftly123')
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse('users'), {'search': 'draftly.demo'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([user['email'] for user in response.data], ['bob@draftly.demo'])


class RegistrationApiTests(APITestCase):
    def setUp(self):
        self.existing = User.objects.create_user('alice', 'alice@draftly.demo', 'draftly123')

    def test_register_creates_the_account_and_returns_a_token(self):
        response = self.client.post(
            reverse('register'),
            {
                'email': 'new.person@draftly.demo',
                'password': 'a-str0ng-passphrase',
                'full_name': 'New Person',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['email'], 'new.person@draftly.demo')
        self.assertTrue(User.objects.filter(email='new.person@draftly.demo').exists())

    def test_register_with_an_existing_email_is_rejected(self):
        response = self.client.post(
            reverse('register'),
            {'email': 'alice@draftly.demo', 'password': 'a-str0ng-passphrase'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_register_with_a_weak_password_is_rejected(self):
        response = self.client.post(
            reverse('register'),
            {'email': 'weak@draftly.demo', 'password': '123'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_register_requires_an_email_address(self):
        response = self.client.post(
            reverse('register'),
            {'password': 'a-str0ng-passphrase'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
