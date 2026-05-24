import json
import logging
import re

from pydantic import ValidationError
from pyramid.response import Response
from pyramid.view import view_config

from playra.clients.rawg import RawgClient
from playra.schemas.games import GameQuery

log = logging.getLogger(__name__)

_GAME_ID_RE = re.compile(r"^[a-z0-9-]+$")


@view_config(route_name="game", renderer="json", permission="authenticated", request_method="GET")
def get_game(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        game_id: str = request.matchdict["id"]

        if not _GAME_ID_RE.match(game_id):
            return Response(json.dumps({"error": "Invalid game ID"}), content_type="application/json", charset="utf-8", status=400)

        game = rawg_client.get_game(game_id)

        return {"data": game.model_dump()}

    except Exception:
        log.exception("Error fetching game %s", game_id)
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)


@view_config(route_name="games", renderer="json", permission="authenticated", request_method="GET")
def get_games(request):
    try:
        rawg_client: RawgClient = request.registry.rawg_client
        query = GameQuery(**request.params)

        games = rawg_client.get_games(query)

        return {"data": games.model_dump()}

    except ValidationError as e:
        return Response(e.json(), content_type="application/json", charset="utf-8", status=400)
    except Exception:
        log.exception("Error fetching games")
        return Response(json.dumps({"error": "An error occurred while fetching data."}), content_type="application/json", charset="utf-8", status=500)
