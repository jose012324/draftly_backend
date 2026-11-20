"""Authentication and user related endpoints for the Draftly API."""

from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


def _authenticate_by_email(request, email, password):
    """Authenticate a user that signs in with their e-mail address."""
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        return None
    return authenticate(request, username=user.username, password=password)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_view(request):
    """GET /api/health/ — public liveness probe for uptime monitors.

    Deliberately does not touch the database: a health check should report
    that the service is up without putting load on the database.
    """
    return Response({'status': 'ok', 'service': 'draftly'})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """POST /api/auth/login/ — exchange e-mail + password for an API token."""
    email = (request.data.get('email') or '').strip()
    password = request.data.get('password') or ''

    if not email or not password:
        return Response(
            {'detail': 'E-mail address and password are required.'},
            status=400,
        )

    user = _authenticate_by_email(request, email, password)
    if user is None:
        return Response(
            {'detail': 'Invalid e-mail address or password.'},
            status=400,
        )

    token, _created = Token.objects.get_or_create(user=user)
    return Response({'token': token.key, 'user': UserSerializer(user).data})


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """POST /api/auth/register/ — create an account and return a token."""
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    token, _created = Token.objects.get_or_create(user=user)
    return Response(
        {'token': token.key, 'user': UserSerializer(user).data},
        status=201,
    )


@api_view(['POST'])
def logout_view(request):
    """POST /api/auth/logout/ — invalidate the current token."""
    if request.auth:
        request.auth.delete()
    return Response(status=204)


@api_view(['GET'])
def me_view(request):
    """GET /api/auth/me/ — the currently signed in user."""
    return Response(UserSerializer(request.user).data)


@api_view(['GET'])
def users_view(request):
    """GET /api/users/?search= — look up people to share a document with."""
    search = (request.query_params.get('search') or '').strip()

    queryset = User.objects.all()
    if search:
        queryset = queryset.filter(
            Q(email__icontains=search)
            | Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    queryset = queryset.exclude(pk=request.user.pk).order_by('email')[:20]
    return Response(UserSerializer(queryset, many=True).data)
