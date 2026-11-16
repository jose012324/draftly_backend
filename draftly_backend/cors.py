"""
Very small CORS middleware for the Draftly frontend.

The React application runs on a different origin (Vite on :5173 in
development, the deployed static host in production), so the browser needs the
usual CORS headers on API responses.

It lives inside the project on purpose: it is a few dozen lines and keeps the
backend free of an extra third-party dependency.
"""

from django.conf import settings
from django.http import HttpResponse

ALLOWED_HEADERS = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"

# Headers the browser may read from a cross origin response (the file name of
# a download lives in "Content-Disposition").
EXPOSED_HEADERS = "Content-Disposition, Content-Length, Content-Type"


class CorsMiddleware:
    """Adds CORS headers to every response when the origin is allowed."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Preflight requests never reach the view.
        if request.method == "OPTIONS" and "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        self._add_cors_headers(request, response)
        return response

    def _add_cors_headers(self, request, response):
        origin = request.META.get("HTTP_ORIGIN")
        allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])

        if not origin or (origin not in allowed_origins and "*" not in allowed_origins):
            return

        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Credentials"] = "true"
        response["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
        response["Access-Control-Allow-Methods"] = ALLOWED_METHODS
        response["Access-Control-Max-Age"] = "86400"

        # Without this the browser hides the headers of a cross origin
        # response — the file name of a download lives in "Content-Disposition".
        response["Access-Control-Expose-Headers"] = EXPOSED_HEADERS
        response["Vary"] = "Origin"
