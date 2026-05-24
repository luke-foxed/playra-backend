import os

import requests

from playra.clients.cache import cached
from playra.schemas.games import GameQuery, GameResponse, GamesResponse

BASE_URL = "https://api.rawg.io/api"
_GAMES_TTL = 60 * 60 * 24        # 24 hours
_GAME_TTL = 60 * 60 * 24 * 7     # 7 days

_client = None


class RawgClient:

    def __init__(self, api_key, cache_client):
        self._params = {"key": api_key}
        self._cache = cache_client

    def _get(self, path, **params) -> dict:
        response = requests.get(
            f"{BASE_URL}{path}",
            params={**self._params, **params},
        )
        response.raise_for_status()
        return response.json()

    # _fetch_* methods are the cache boundary — raw dicts only.
    # get_* methods are the public API — always return typed models.

    @cached(table="game_queries", key_fn=lambda query: query.to_params(), ttl_seconds=_GAMES_TTL)
    def _fetch_games(self, query: GameQuery) -> dict:
        return self._get("/games", **query.to_params())

    def get_games(self, query: GameQuery) -> GamesResponse:
        return GamesResponse(**self._fetch_games(query))

    @cached(table="games", key_fn=lambda slug_or_id: slug_or_id, ttl_seconds=_GAME_TTL)
    def _fetch_game(self, slug_or_id: str) -> dict:
        return self._get(f"/games/{slug_or_id}")

    def get_game(self, slug_or_id: str) -> GameResponse:
        return GameResponse(**self._fetch_game(slug_or_id))


def get_rawg_client(cache_client) -> RawgClient:
    global _client
    if _client is None:
        api_key = os.environ.get("RAWG_API_KEY")
        if not api_key:
            raise RuntimeError("RAWG_API_KEY environment variable is not set")
        _client = RawgClient(api_key, cache_client)
    return _client
