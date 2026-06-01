import json
import logging
import re
from collections import defaultdict

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config
from requests.exceptions import HTTPError

from playra.auth.decorators import require_role
from playra.clients.rawg import RawgClient
from playra.schemas.games import GameQuery, GamesResponse

log = logging.getLogger(__name__)


def _get_community_score(game_id: int, supabase_client) -> float | None:
    rows = (
        supabase_client.table("list_games")
        .select("user_rating")
        .eq("game_id", game_id)
        .not_.is_("user_rating", "null")
        .execute().data
    )
    scores = [r["user_rating"] for r in rows]
    return round(sum(scores) / len(scores), 2) if scores else None


def _attach_community_ratings(games_response: GamesResponse, supabase_client) -> None:
    game_ids = [g.id for g in games_response.results]
    if not game_ids:
        return

    rows = (
        supabase_client.table("list_games")
        .select("game_id, user_rating")
        .in_("game_id", game_ids)
        .not_.is_("user_rating", "null")
        .execute().data
    )

    totals = defaultdict(list)
    for row in rows:
        totals[row["game_id"]].append(row["user_rating"])

    for game in games_response.results:
        scores = totals.get(game.id)
        game.playra_community_score = round(sum(scores) / len(scores), 2) if scores else None

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
        game.playra_community_score = _get_community_score(game.id, request.registry.supabase_client)

        return {"data": game.model_dump(mode="json"), "from_cache": game.from_cache}

    except HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return Response(json.dumps({"error": "Game not found"}), content_type="application/json", charset="utf-8", status=404)
        log.exception("RAWG error fetching game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)
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
        ratings_entry = next((e for e in entries if e["lists"]["type"] == "ratings"), None)
        rating = ratings_entry["user_rating"] if ratings_entry else None
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


@view_config(route_name="game_screenshots", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_game_screenshots(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        game_id: str = request.matchdict["id"]
        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)
        screenshots = rawg_client.get_game_screenshots(game_id)
        return {"data": screenshots.model_dump(mode="json"), "from_cache": screenshots.from_cache}
    except Exception:
        log.exception("Error fetching screenshots for game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="game_series", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_game_series(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        game_id: str = request.matchdict["id"]
        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)
        series = rawg_client.get_game_series(game_id)
        return {"data": series.model_dump(mode="json"), "from_cache": series.from_cache}
    except Exception:
        log.exception("Error fetching series for game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="genres", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_genres(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        genres = rawg_client.get_genres()
        return {"data": genres.model_dump(mode="json"), "from_cache": genres.from_cache}
    except Exception:
        log.exception("Error fetching genres")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_games(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        query = GameQuery(**request.params)

        games = rawg_client.get_games(query)
        _attach_community_ratings(games, request.registry.supabase_client)

        return {"data": games.model_dump(mode="json"), "from_cache": games.from_cache}

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
        _attach_community_ratings(games, request.registry.supabase_client)

        return {"data": games.model_dump(mode="json"), "from_cache": games.from_cache}

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
        _attach_community_ratings(games, request.registry.supabase_client)

        return {"data": games.model_dump(mode="json"), "from_cache": games.from_cache}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error fetching recent games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)
