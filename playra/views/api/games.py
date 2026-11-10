import json
import logging
import re
from collections import defaultdict

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config

from playra.auth.decorators import require_role
from playra.clients.igdb import IgdbClient, IgdbHTTPError, IgdbNotFoundError, IgdbUnavailableError
from playra.schemas.games import GameQuery, GamesResponse

log = logging.getLogger(__name__)

# Statuses that mean "IGDB is having a bad time", not "the request was wrong".
_UPSTREAM_DOWN_STATUSES = frozenset({429, 500, 502, 503, 504})


def _igdb_error_response(context: str, exc: Exception) -> Response:
    """503 when IGDB (or the Twitch OAuth token endpoint) itself is down, 500 for
    anything we might have caused. IgdbUnavailableError already covers both IGDB
    call failures and token-fetch failures, so no special-casing is needed for
    "the OAuth handshake failed" vs. "the actual games endpoint failed"."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(exc, IgdbUnavailableError) or status in _UPSTREAM_DOWN_STATUSES:
        # No stack trace: an upstream outage is not a bug in our code, and at one log
        # entry per request these tracebacks bury everything else.
        log.warning("%s: IGDB unavailable (%s)", context, exc)
        response = Response(
            json.dumps({"error": "Game data is temporarily unavailable. Please try again shortly."}),
            content_type="application/json",
            charset="utf-8",
            status=503,
        )
        response.headers["Retry-After"] = "30"
        return response

    log.exception("%s: unexpected IGDB error", context)
    return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


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

# IGDB is numeric-id-only -- no slug lookup.
_GAME_ID_RE = re.compile(r"^\d+$")


@view_config(route_name="game", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_game(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        game_id: str = request.matchdict["id"]

        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)

        game = igdb_client.get_game(int(game_id))
        game.playra_community_score = _get_community_score(game.id, request.registry.supabase_client)

        return {"data": game.model_dump(mode="json"), "from_cache": game.from_cache}

    except IgdbNotFoundError:
        return Response(json.dumps({"error": "Game not found"}), content_type="application/json", charset="utf-8", status=404)
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response(f"Error fetching game {game_id}", e)
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
        igdb_client: IgdbClient = request.registry.igdb_client
        game_id: str = request.matchdict["id"]
        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)
        screenshots = igdb_client.get_game_screenshots(int(game_id))
        return {"data": screenshots.model_dump(mode="json"), "from_cache": screenshots.from_cache}
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response(f"Error fetching screenshots for game {game_id}", e)
    except Exception:
        log.exception("Error fetching screenshots for game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="game_related", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_game_related(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        game_id: str = request.matchdict["id"]
        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)
        related = igdb_client.get_game_related(int(game_id))
        return {"data": related.model_dump(mode="json"), "from_cache": related.from_cache}
    except IgdbNotFoundError:
        return Response(json.dumps({"error": "Game not found"}), content_type="application/json", charset="utf-8", status=404)
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response(f"Error fetching related games for {game_id}", e)
    except Exception:
        log.exception("Error fetching related games for %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="genres", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_genres(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        genres = igdb_client.get_genres()
        return {"data": genres.model_dump(mode="json"), "from_cache": genres.from_cache}
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response("Error fetching genres", e)
    except Exception:
        log.exception("Error fetching genres")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="platforms", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_platforms(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        platforms = igdb_client.get_platforms()
        return {"data": platforms.model_dump(mode="json"), "from_cache": platforms.from_cache}
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response("Error fetching platforms", e)
    except Exception:
        log.exception("Error fetching platforms")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_games(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        query = GameQuery(**request.params)

        games = igdb_client.get_games(query)
        _attach_community_ratings(games, request.registry.supabase_client)

        return {"data": games.model_dump(mode="json"), "from_cache": games.from_cache}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response("Error fetching games", e)
    except Exception:
        log.exception("Error fetching games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games_popular", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_popular_games(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        query = GameQuery(**request.params)

        games = igdb_client.get_popular_games(query)
        _attach_community_ratings(games, request.registry.supabase_client)

        return {"data": games.model_dump(mode="json"), "from_cache": games.from_cache}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response("Error fetching popular games", e)
    except Exception:
        log.exception("Error fetching popular games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games_recent", renderer="json", permission="authenticated", request_method="GET")
@require_role("active", "admin")
def get_recent_games(request):
    try:
        igdb_client: IgdbClient = request.registry.igdb_client
        query = GameQuery(**request.params)

        games = igdb_client.get_recent_games(query)
        _attach_community_ratings(games, request.registry.supabase_client)

        return {"data": games.model_dump(mode="json"), "from_cache": games.from_cache}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except (IgdbUnavailableError, IgdbHTTPError) as e:
        return _igdb_error_response("Error fetching recent games", e)
    except Exception:
        log.exception("Error fetching recent games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)
