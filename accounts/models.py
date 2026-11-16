"""The user model used by Draftly.

Draftly re-uses Django's built-in ``User`` model (the plan explicitly allows
it: a custom user model is only needed when the initial migrations have to
change). It is re-exported here so the rest of the project can simply do
``from accounts.models import User``.
"""

from django.contrib.auth.models import User

__all__ = ['User']
