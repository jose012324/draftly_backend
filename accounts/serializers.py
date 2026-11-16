"""Serializers for user data exposed by the API."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Public representation of a user (safe to share with other users)."""

    full_name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'full_name', 'initials']
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_initials(self, obj):
        name = self.get_full_name(obj)
        parts = name.split()
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class RegisterSerializer(serializers.Serializer):
    """Payload of the registration form."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                'An account with this e-mail address already exists.'
            )
        return email

    def validate_password(self, value):
        # Uses the AUTH_PASSWORD_VALIDATORS of the project.
        validate_password(value)
        return value

    def create(self, validated_data):
        email = validated_data['email']
        full_name = validated_data.get('full_name', '').strip()
        first_name, _, last_name = full_name.partition(' ')

        user = User.objects.create_user(
            username=self._unique_username(email),
            email=email,
            password=validated_data['password'],
            first_name=first_name[:150],
            last_name=last_name[:150],
        )
        return user

    def _unique_username(self, email):
        """Derive a free username from the e-mail address."""
        base = email.split('@')[0].replace('.', '_').replace('+', '_') or 'user'
        username = base
        counter = 1
        while User.objects.filter(username=username).exists():
            counter += 1
            username = f'{base}{counter}'
        return username[:150]
