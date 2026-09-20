import logging

from pyramid.view import view_config

from playra.clients.supabase import get_supabase_client

log = logging.getLogger(__name__)


@view_config(route_name="home", renderer="json", permission="authenticated")
def my_view(request):
    return {"status": "ok"}


@view_config(route_name="health", renderer="json", request_method="GET")
def health_check(request):
    try:
        client = get_supabase_client()
        client.table("profiles").select("id").limit(1).execute()
        return {"status": "ok", "db": "reachable"}
    except Exception as e:
        request.response.status_int = 503
        return {"status": "error", "db": str(e)}
