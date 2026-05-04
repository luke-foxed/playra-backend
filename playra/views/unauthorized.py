from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.view import exception_view_config


@exception_view_config(HTTPUnauthorized, renderer="json")
def unauthorized_view(exc, request):
    request.response.status = 401

    return {
        "error": "unauthorized",
        "message": "Authentication required"
    }