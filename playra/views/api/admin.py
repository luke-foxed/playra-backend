import json
import logging

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config

from playra.auth.decorators import require_role
from playra.schemas.profile import ProfileResponse, RoleUpdateRequest

log = logging.getLogger(__name__)


@view_config(route_name="admin_users", renderer="json", permission="authenticated", request_method="GET")
@require_role("admin")
def get_all_users(request):
    try:
        supabase_client = request.registry.supabase_client
        data = supabase_client.table("profiles").select("*").order("created_at", desc=True).execute().data
        users = [ProfileResponse(**row).model_dump(mode="json") for row in data]
        return {"data": users}
    except Exception:
        log.exception("Error fetching all users")
        return Response(json.dumps({"error": "An error occurred."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="admin_user_role", renderer="json", permission="authenticated", request_method="PATCH")
@require_role("admin")
def update_user_role(request):
    user_id = request.matchdict["user_id"]
    try:
        body = RoleUpdateRequest(**request.json_body)
    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)

    try:
        supabase_client = request.registry.supabase_client
        supabase_client.table("profiles").update({"role": body.role}).eq("id", user_id).execute()
        return {"message": f"Role updated to '{body.role}'"}
    except Exception:
        log.exception("Error updating role for user %s", user_id)
        return Response(json.dumps({"error": "An error occurred."}), content_type="application/json", charset="utf-8", status=500)
