from pyramid.httpexceptions import HTTPForbidden
from pyramid.view import exception_view_config


@exception_view_config(HTTPForbidden, renderer="json")
def forbidden_view(exc, request):
    request.response.status = 403
    return {
        "error": "forbidden",
        "message": "You do not have permission to access this resource"
    }