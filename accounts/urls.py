"""URLs for the authentication and user endpoints."""

from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health_view, name='health'),
    path('auth/login/', views.login_view, name='login'),
    path('auth/register/', views.register_view, name='register'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/me/', views.me_view, name='me'),
    path('users/', views.users_view, name='users'),
]
