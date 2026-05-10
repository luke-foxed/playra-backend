from pyramid.response import Response
from pyramid.view import view_config
from playra.schemas.games import GameQuery


@view_config(route_name="game", renderer="json", permission="authenticated", request_method="GET")
def get_game(request):
    try:
        rawg_client = request.registry.rawg_client
        game_id = request.matchdict["id"]

        game = rawg_client.get_game(game_id)

        return {"data": game}

    except Exception as e:
        return Response(
            f"An error occurred while fetching data: {str(e)}",
            content_type="text/plain",
            status=500,
        )


@view_config(route_name="games", renderer="json", permission="authenticated", request_method="GET")
def get_games(request):
    try:
        rawg_client = request.registry.rawg_client

        query = GameQuery(**request.params)

        games = rawg_client.get_games(query)

        return {"data": games}

    except Exception as e:
        return Response(
            f"An error occurred while fetching data: {str(e)}",
            content_type="text/plain",
            status=500,
        )
