import json
import logging

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config

from playra.auth.decorators import require_role
from playra.schemas.lists import ListGamesAddRequest, ListGamesDeleteRequest, ListQuery, ListRequest

log = logging.getLogger(__name__)


@view_config(route_name="lists", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_lists(request):
    current_user_id = request.authenticated_userid

    try:
        params = ListQuery(
            page=request.params.get("page", 1),
            page_size=request.params.get("page_size", 20),
            ordering=request.params.get("ordering"),
        )
    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)

    target_user_id = request.params.get("user_id", current_user_id)
    is_own = target_user_id == current_user_id

    offset = (params.page - 1) * params.page_size

    try:
        supabase_client = request.registry.supabase_client

        query = supabase_client.table("lists").select("*").eq("created_by", target_user_id)

        if not is_own:
            query = query.eq("is_public", True)

        if params.ordering:
            desc = params.ordering.startswith("-")
            column = params.ordering.lstrip("-")
            query = query.order(column, desc=desc)

        query = query.range(offset, offset + params.page_size - 1)

        data = query.execute().data

        return {"data": data, "page": params.page, "page_size": params.page_size}

    except Exception:
        log.exception("Error fetching lists for user %s", target_user_id)
        return Response(json.dumps({"error": "An error occurred while fetching lists."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="lists", renderer="json", permission="authenticated", request_method="POST")
@require_role("active", "admin")
def create_list(request):
    current_user_id = request.authenticated_userid

    try:
        supabase_client = request.registry.supabase_client
        list_model = ListRequest(**request.json_body)
        new_list = supabase_client.table("lists").insert({
            **list_model.model_dump(),
            "type": "custom",
            "created_by": current_user_id,
        }).execute().data[0]

        return {"data": new_list}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error creating list for user %s", current_user_id)
        return Response(json.dumps({"error": "An error occurred while creating the list."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="list", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_list(request):
    user_list_id: str = request.matchdict["id"]

    try:
        supabase_client = request.registry.supabase_client

        user_list = supabase_client.table("lists").select("*").eq("id", user_list_id).single().execute().data
        user_list_games = supabase_client.table("list_games").select("*").eq("list_id", user_list_id).execute().data

        return {"data": {**user_list, "games": user_list_games}}

    except Exception:
        log.exception("Error fetching list %s", user_list_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="list", renderer="json", permission="authenticated", request_method="PUT")
@require_role("active", "admin")
def update_list(request):
    current_user_id = request.authenticated_userid
    user_list_id: str = request.matchdict["id"]

    try:
        supabase_client = request.registry.supabase_client

        list_model = ListRequest(**request.json_body)
        list_updates = list_model.model_dump(exclude_none=True)
        supabase_client.table("lists").update(list_updates).eq("id", user_list_id).eq("created_by", current_user_id).execute()

        return {"message": "List updated successfully"}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error updating list %s", user_list_id)
        return Response(json.dumps({"error": "An error occurred while updating the list."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="list", renderer="json", permission="authenticated", request_method="DELETE")
@require_role("active", "admin")
def delete_list(request):
    current_user_id = request.authenticated_userid
    user_list_id: str = request.matchdict["id"]

    try:
        supabase_client = request.registry.supabase_client
        supabase_client.table("lists").delete().eq("id", user_list_id).eq("created_by", current_user_id).execute()

        return {"message": "List deleted successfully"}

    except Exception:
        log.exception("Error deleting list %s", user_list_id)
        return Response(json.dumps({"error": "An error occurred while deleting the list."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="list_games", renderer="json", permission="authenticated", request_method="POST")
@require_role("active", "admin")
def add_games_to_list(request):
    user_list_id: str = request.matchdict["id"]

    try:
        supabase_client = request.registry.supabase_client
        batch = ListGamesAddRequest(**request.json_body)

        entries = [
            {
                "list_id": user_list_id,
                "game_id": g.game_id,
                "name": g.name,
                "released": str(g.released) if g.released else None,
                "genres": g.genres,
                "metacritic": g.metacritic,
                "background_image": g.background_image,
                "user_rating": g.user_rating,
            }
            for g in batch.games
        ]

        supabase_client.table("list_games").upsert(entries).execute()

        return {"message": f"{len(entries)} game(s) added successfully"}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error adding games to list %s", user_list_id)
        return Response(json.dumps({"error": "An error occurred while adding games."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="list_games", renderer="json", permission="authenticated", request_method="DELETE")
@require_role("active", "admin")
def remove_games_from_list(request):
    user_list_id: str = request.matchdict["id"]

    try:
        supabase_client = request.registry.supabase_client
        batch = ListGamesDeleteRequest(**request.json_body)

        supabase_client.table("list_games").delete().eq("list_id", user_list_id).in_("game_id", batch.game_ids).execute()

        return {"message": f"{len(batch.game_ids)} game(s) removed successfully"}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error removing games from list %s", user_list_id)
        return Response(json.dumps({"error": "An error occurred while removing games."}), content_type="application/json", charset="utf-8", status=500)


