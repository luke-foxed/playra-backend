from pyramid.httpexceptions import HTTPForbidden
from pyramid.view import exception_view_config


@exception_view_config(HTTPForbidden, renderer="json")
def forbidden_view(exc, request):
    if getattr(request, "auth_token_invalid", False):
        request.response.status = 401
        return {"error": "unauthorized", "message": "Invalid or expired token"}

    request.response.status = 403
    return {"error": "forbidden", "message": "You do not have permission to access this resource"}