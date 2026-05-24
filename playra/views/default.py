import logging

from pyramid.view import view_config

log = logging.getLogger(__name__)


@view_config(route_name="home", renderer="json", permission="authenticated")
def my_view(request):
    return {"status": "ok"}
