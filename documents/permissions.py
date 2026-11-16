"""Access rules for documents.

Every check happens on the server: the frontend only hides buttons, the API is
the one that decides whether an action is allowed.
"""

ROLE_OWNER = 'owner'
ROLE_EDITOR = 'editor'
ROLE_VIEWER = 'viewer'


def get_role(document, user):
    """The role of ``user`` on ``document`` (owner, editor, viewer or None)."""
    if user is None or not user.is_authenticated:
        return None

    if document.owner_id == user.id:
        return ROLE_OWNER

    permission = document.permissions.filter(user=user).first()
    return permission.role if permission else None


def can_view(document, user):
    """True when the user owns the document or it was shared with them."""
    return get_role(document, user) is not None


def can_edit(document, user):
    """True for the owner and for users with the editor role."""
    return get_role(document, user) in (ROLE_OWNER, ROLE_EDITOR)


def is_owner(document, user):
    """True only for the owner of the document."""
    return get_role(document, user) == ROLE_OWNER
