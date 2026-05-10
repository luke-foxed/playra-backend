import os
import requests
from playra.schemas.games import GameQuery
from playra.clients.cache import cached


BASE_URL = "https://api.rawg.io/api"
_client = None

class RawgClient:

    def __init__(self, api_key, cache_client):
        self._params = {"key": api_key}
        self._cache = cache_client

    def _get(self, path, **params):
        response = requests.get(
            f"{BASE_URL}{path}",
            params={**self._params, **params},
        )
        response.raise_for_status()
        return response.json()
    
    # Games functions
    @cached(table="game_queries", key_fn=lambda query: query.to_params(), ttl_seconds=60 * 60 * 24)
    def get_games(self, query: GameQuery):
        return self._get("/games", **query.to_params())

    # Game functions
    @cached(table="games", key_fn=lambda slug_or_id: slug_or_id, ttl_seconds=60 * 60 * 24 * 7)
    def get_game(self, slug_or_id):
        return self._get(f"/games/{slug_or_id}")
    
    def get_series_of_game(self, game_pk):
        return self._get(f"/games/{game_pk}/game-series")



def get_rawg_client(cache_client) -> RawgClient:
    global _client
    if _client is None:
        api_key = os.environ.get("RAWG_API_KEY")
        if not api_key:
            raise RuntimeError("RAWG_API_KEY environment variable is not set")
        _client = RawgClient(api_key, cache_client)
    return _client