import json
import logging
import re

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config

from playra.auth.decorators import require_role
from playra.clients.rawg import RawgClient
from playra.schemas.games import GameQuery

log = logging.getLogger(__name__)

_GAME_ID_RE = re.compile(r"^[a-z0-9-]+$")


@view_config(route_name="game", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_game(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        game_id: str = request.matchdict["id"]

        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)

        game = rawg_client.get_game(game_id)

        return {"data": game.model_dump(mode="json")}

    except Exception:
        log.exception("Error fetching game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="game_user", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_game_user_context(request):
    current_user_id = request.authenticated_userid

    try:
        game_id = int(request.matchdict["id"])
    except ValueError:
        return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)

    try:
        supabase_client = request.registry.supabase_client

        entries = (
            supabase_client.table("list_games")
            .select("user_rating, lists!inner(id, name, type)")
            .eq("game_id", game_id)
            .eq("lists.created_by", current_user_id)
            .execute().data
        )

        in_wishlist = any(e["lists"]["type"] == "wishlist" for e in entries)
        playlist_entry = next((e for e in entries if e["lists"]["type"] == "playlist"), None)
        rating = playlist_entry["user_rating"] if playlist_entry else None
        custom_lists = [{"id": e["lists"]["id"], "name": e["lists"]["name"]} for e in entries if e["lists"]["type"] == "custom"]

        return {
            "data": {
                "in_wishlist": in_wishlist,
                "rating": rating,
                "lists": custom_lists,
            }
        }

    except Exception:
        log.exception("Error fetching user context for game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching user context."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_games(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        query = GameQuery(**request.params)

        games = rawg_client.get_games(query)

        return {"data": games.model_dump(mode="json")}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error fetching games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games_popular", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_popular_games(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        query = GameQuery(**request.params)

        games = rawg_client.get_popular_games(query)

        return {"data": games.model_dump(mode="json")}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error fetching popular games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games_recent", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_recent_games(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        query = GameQuery(**request.params)

        games = rawg_client.get_recent_games(query)

        return {"data": games.model_dump(mode="json")}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error fetching recent games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)
