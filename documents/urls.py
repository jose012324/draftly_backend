"""URLs for the document endpoints.

The canonical paths follow the API specification:

    GET    /api/documents/                             list
    POST   /api/documents/                             create
    POST   /api/documents/import/                      import a file
    GET    /api/documents/<id>/                        read
    PATCH  /api/documents/<id>/                        update
    DELETE /api/documents/<id>/                        move to trash
    POST   /api/documents/<id>/restore/                restore
    DELETE /api/documents/<id>/purge/                  delete permanently
    GET    /api/documents/<id>/permissions/            list permissions
    POST   /api/documents/<id>/share/                  grant access
    PATCH  /api/documents/<id>/permissions/<pid>/      change a role
    DELETE /api/documents/<id>/share/<user_id>/        revoke access

The ``shares`` routes are kept as aliases of the older naming.
"""

from django.urls import path

from . import views

urlpatterns = [
    path('documents/', views.document_list, name='document-list'),
    path('documents/import/', views.document_import, name='document-import'),
    path('documents/<uuid:pk>/', views.document_detail, name='document-detail'),
    path('documents/<uuid:pk>/version/', views.document_version, name='document-version'),
    path('documents/<uuid:pk>/download/', views.document_download, name='document-download'),
    path('documents/<uuid:pk>/restore/', views.document_restore, name='document-restore'),
    path('documents/<uuid:pk>/purge/', views.document_purge, name='document-purge'),

    # Sharing — canonical paths
    path(
        'documents/<uuid:pk>/permissions/',
        views.document_permissions,
        name='document-permissions',
    ),
    path('documents/<uuid:pk>/share/', views.document_share, name='document-share'),
    path(
        'documents/<uuid:pk>/permissions/<int:permission_id>/',
        views.document_permission_detail,
        name='document-permission-detail',
    ),
    path(
        'documents/<uuid:pk>/share/<int:user_id>/',
        views.document_share_revoke,
        name='document-share-revoke',
    ),

    # Sharing — legacy aliases
    path('documents/<uuid:pk>/shares/', views.document_shares, name='document-shares'),
    path('documents/<uuid:pk>/shares/<int:share_id>/', views.document_share_detail, name='document-share-detail'),
]
