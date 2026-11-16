"""Document endpoints: listing, CRUD, importing and sharing.

The views are intentionally thin — every rule lives in
``documents/permissions.py`` (who may do what) and ``documents/services.py``
(what happens).
"""

import json

from django.http import FileResponse, HttpResponse
from django.utils.text import slugify
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .docx_export import to_docx
from .exports import to_html, to_markdown
from .importers import UnsupportedFileError, import_uploaded_file
from .models import DocumentPermission
from .realtime import broadcast_document_update
from .serializers import (
    DocumentCreateSerializer,
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentUpdateSerializer,
    ShareSerializer,
)
from .services import (
    ServiceError,
    change_permission,
    create_document,
    get_document_for,
    list_documents,
    list_permissions,
    purge_document,
    restore_document,
    revoke_permission,
    share_document,
    soft_delete_document,
    update_document,
)
from .tiptap import extract_text


def _serialize(document, request):
    return DocumentDetailSerializer(document, context={'request': request}).data


def _serialize_list(documents, request):
    return DocumentListSerializer(documents, many=True, context={'request': request}).data


DOCX_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
)


def _file_response(field, content_type, filename):
    """Send a stored file as a download."""
    field.open('rb')
    response = FileResponse(
        field,
        content_type=content_type,
        as_attachment=True,
        filename=filename,
    )
    response['Content-Length'] = field.size or 0
    return response


def _error(error):
    """Turn a ServiceError into a JSON response."""
    return Response({'detail': error.message}, status=error.status_code)


@api_view(['GET', 'POST'])
def document_list(request):
    """GET  /api/documents/ — list the documents visible to the user.

    GET  ?scope=mine|shared|recent|trash &search=keyword
    POST /api/documents/ — create a new document.
    """
    if request.method == 'POST':
        serializer = DocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            document = create_document(
                request.user,
                title=serializer.validated_data.get('title'),
                content=serializer.validated_data.get('content'),
            )
        except ServiceError as error:
            return _error(error)

        return Response(_serialize(document, request), status=201)

    scope = request.query_params.get('scope', 'all')
    search = request.query_params.get('search', '')
    documents = list_documents(request.user, scope=scope, search=search)

    return Response(_serialize_list(documents, request))


@api_view(['GET'])
def document_version(request, pk):
    """GET /api/documents/<id>/version/ — the current version of a document.

    A cheap endpoint (no content) that the editor polls when the WebSocket is
    not available, to notice that somebody else changed the document.
    """
    try:
        document = get_document_for(request.user, pk)
    except ServiceError as error:
        return _error(error)

    return Response(
        {
            'id': str(document.id),
            'version': document.version,
            'updated_at': document.updated_at,
        }
    )


@api_view(['GET'])
def document_download(request, pk):
    """GET /api/documents/<id>/download/?format=docx|original|md|html|txt|json

    Everybody who can read the document may download it.

    * ``docx``    — the stored Word file (the default)
    * ``original`` — the file that was uploaded, for an imported document
    * ``md`` / ``html`` / ``txt`` / ``json`` — generated from the content
    """
    try:
        document = get_document_for(request.user, pk)
    except ServiceError as error:
        return _error(error)

    export_format = (request.query_params.get('format') or 'docx').lower()
    filename = slugify(document.title) or 'document'

    # The original upload of an imported document.
    if export_format == 'original':
        if not document.source_file:
            return Response(
                {'detail': 'This document was not imported — there is no original file.'},
                status=404,
            )

        return _file_response(
            document.source_file,
            content_type='application/octet-stream',
            filename=document.source_filename or f'{filename}',
        )

    # The stored Word file.
    if export_format == 'docx':
        if document.file:
            return _file_response(
                document.file,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                filename=f'{filename}.docx',
            )

        # Fall back to a freshly generated file for documents that were created
        # before the file existed.
        payload = to_docx(document.content, title=document.title)
        response = HttpResponse(payload, content_type=DOCX_CONTENT_TYPE)
        response['Content-Disposition'] = f'attachment; filename="{filename}.docx"'
        return response

    if export_format == 'json':
        body = json.dumps(document.content, ensure_ascii=False, indent=2)
        content_type = 'application/json; charset=utf-8'
        extension = 'json'
    elif export_format == 'md':
        body = to_markdown(document.content)
        content_type = 'text/markdown; charset=utf-8'
        extension = 'md'
    elif export_format == 'html':
        body = to_html(document.content, title=document.title)
        content_type = 'text/html; charset=utf-8'
        extension = 'html'
    else:
        body = extract_text(document.content)
        content_type = 'text/plain; charset=utf-8'
        extension = 'txt'

    response = HttpResponse(body, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}.{extension}"'
    return response


@api_view(['GET', 'PATCH', 'DELETE'])
def document_detail(request, pk):
    """GET    /api/documents/<id>/ — read a document.

    PATCH  /api/documents/<id>/ — update title/content (owner or editor).
    DELETE /api/documents/<id>/ — move the document to the trash (owner).
    """
    try:
        document = get_document_for(request.user, pk)
    except ServiceError as error:
        return _error(error)

    if request.method == 'GET':
        return Response(_serialize(document, request))

    if request.method == 'PATCH':
        serializer = DocumentUpdateSerializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            document = update_document(
                document,
                request.user,
                title=serializer.validated_data.get('title'),
                content=serializer.validated_data.get('content'),
            )
        except ServiceError as error:
            return _error(error)

        # Let everybody who has the document open see the change.
        broadcast_document_update(document, request.user)

        return Response(_serialize(document, request))

    # DELETE -> move to trash
    try:
        soft_delete_document(document, request.user)
    except ServiceError as error:
        return _error(error)

    return Response(status=204)


@api_view(['POST'])
def document_restore(request, pk):
    """POST /api/documents/<id>/restore/ — bring a document back from the trash."""
    try:
        document = get_document_for(request.user, pk)
        restore_document(document, request.user)
    except ServiceError as error:
        return _error(error)

    return Response(_serialize(document, request))


@api_view(['DELETE'])
def document_purge(request, pk):
    """DELETE /api/documents/<id>/purge/ — delete a document permanently."""
    try:
        document = get_document_for(request.user, pk)
        purge_document(document, request.user)
    except ServiceError as error:
        return _error(error)

    return Response(status=204)


@api_view(['POST'])
def document_import(request):
    """POST /api/documents/import/ — import a .txt, .md or .docx file."""
    uploaded_file = request.FILES.get('file')

    if uploaded_file is None:
        return Response({'detail': 'No file was uploaded.'}, status=400)

    try:
        title, content = import_uploaded_file(uploaded_file)
    except UnsupportedFileError as error:
        return Response({'detail': str(error)}, status=400)
    except ValueError as error:
        return Response({'detail': str(error)}, status=400)

    try:
        document = create_document(
            request.user,
            title=title,
            content=content,
            source_filename=uploaded_file.name,
        )
    except ServiceError as error:
        return _error(error)

    # Keep the uploaded file as it was — it can be downloaded again as
    # "original".
    try:
        uploaded_file.seek(0)
        document.source_file.save(
            uploaded_file.name,
            uploaded_file,
            save=False,
        )
        document.save(update_fields=['source_file'])
    except Exception:
        pass

    return Response(_serialize(document, request), status=201)


@api_view(['GET'])
def document_permissions(request, pk):
    """GET /api/documents/<id>/permissions/ — everyone that has access."""
    try:
        document = get_document_for(request.user, pk)
    except ServiceError as error:
        return _error(error)

    return Response(ShareSerializer(list_permissions(document), many=True).data)


@api_view(['POST'])
def document_share(request, pk):
    """POST /api/documents/<id>/share/ — grant access to the document (owner only)."""
    try:
        document = get_document_for(request.user, pk)
        permission, created = share_document(
            document,
            request.user,
            email=request.data.get('email'),
            role=request.data.get('role'),
        )
    except ServiceError as error:
        return _error(error)

    return Response(ShareSerializer(permission).data, status=201 if created else 200)


@api_view(['PATCH'])
def document_permission_detail(request, pk, permission_id):
    """PATCH /api/documents/<id>/permissions/<permission_id>/ — change a role."""
    try:
        document = get_document_for(request.user, pk)
        permission = change_permission(
            document,
            request.user,
            permission_id,
            request.data.get('role'),
        )
    except ServiceError as error:
        return _error(error)

    return Response(ShareSerializer(permission).data)


@api_view(['DELETE'])
def document_share_revoke(request, pk, user_id):
    """DELETE /api/documents/<id>/share/<user_id>/ — revoke the access of a user."""
    try:
        document = get_document_for(request.user, pk)
        revoke_permission(document, request.user, user_id)
    except ServiceError as error:
        return _error(error)

    return Response(status=204)


@api_view(['GET', 'POST'])
def document_shares(request, pk):
    """Legacy alias: GET lists the permissions, POST grants access."""
    try:
        document = get_document_for(request.user, pk)

        if request.method == 'GET':
            return Response(ShareSerializer(list_permissions(document), many=True).data)

        permission, created = share_document(
            document,
            request.user,
            email=request.data.get('email'),
            role=request.data.get('role'),
        )
    except ServiceError as error:
        return _error(error)

    return Response(ShareSerializer(permission).data, status=201 if created else 200)


@api_view(['PATCH', 'DELETE'])
def document_share_detail(request, pk, share_id):
    """Legacy alias: PATCH the role / DELETE the permission by permission id."""
    try:
        document = get_document_for(request.user, pk)

        if request.method == 'PATCH':
            permission = change_permission(
                document,
                request.user,
                share_id,
                request.data.get('role'),
            )
            return Response(ShareSerializer(permission).data)

        revoke_permission(document, request.user, _user_id_for_permission(document, share_id))
    except ServiceError as error:
        return _error(error)

    return Response(status=204)


def _user_id_for_permission(document, permission_id):
    """The user id of a permission (used by the legacy delete alias)."""
    permission = DocumentPermission.objects.filter(id=permission_id, document=document).first()
    if permission is None:
        raise ServiceError('Permission not found.', status_code=404)
    return permission.user_id
