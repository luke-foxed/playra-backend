import json
import logging

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config

from playra.auth.decorators import require_role
from playra.schemas.profile import ProfileRequest, ProfileResponse

log = logging.getLogger(__name__)


@view_config(route_name="profile", renderer="json", permission="authenticated", request_method="GET")
def get_profile(request):
    current_user_id = request.authenticated_userid
    supabase_client = request.registry.supabase_client

    if request.matchdict.get("user_id") != current_user_id:
        log.warning("Unauthorized access attempt to profile %s by user %s", request.matchdict.get("user_id"), current_user_id)
        return Response(json.dumps({"error": "Unauthorized"}), content_type="application/json", charset="utf-8", status=401)

    try:
        data = supabase_client.table("profiles").select("*").eq("id", current_user_id).single().execute().data
        user = ProfileResponse(**data)
        return {"data": user.model_dump(mode="json")}
    except Exception:
        log.exception("Error fetching profile for user %s", current_user_id)
        return Response(json.dumps({"error": "An error occurred."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="profile", renderer="json", permission="authenticated", request_method="PATCH")
@require_role("active", "admin")
def update_profile(request):
    current_user_id = request.authenticated_userid
    supabase_client = request.registry.supabase_client

    if request.matchdict.get("user_id") != current_user_id:
        log.warning("Unauthorized access attempt to profile %s by user %s", request.matchdict.get("user_id"), current_user_id)
        return Response(json.dumps({"error": "Unauthorized"}), content_type="application/json", charset="utf-8", status=401)

    try:
        profile = ProfileRequest(**request.json_body)
        updates = profile.model_dump(exclude_none=True)
        supabase_client.table("profiles").update(updates).eq("id", current_user_id).execute()
        return {"message": "Profile updated successfully"}
    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error updating profile for user %s", current_user_id)
        return Response(json.dumps({"error": "An error occurred."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="profile", renderer="json", permission="authenticated", request_method="DELETE")
@require_role("active", "admin")
def delete_profile(request):
    current_user_id = request.authenticated_userid
    if request.matchdict.get("user_id") != current_user_id:
        log.warning("Unauthorized access attempt to delete profile %s by user %s", request.matchdict.get("user_id"), current_user_id)
        return Response(json.dumps({"error": "Unauthorized"}), content_type="application/json", charset="utf-8", status=401)
    return Response(json.dumps({"error": "Not implemented"}), content_type="application/json", charset="utf-8", status=501)
