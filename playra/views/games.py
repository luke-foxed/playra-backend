from pyramid.response import Response
from pyramid.view import view_config


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
