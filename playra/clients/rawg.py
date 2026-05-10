import os
import requests


BASE_URL = "https://api.rawg.io/api"

_client = None


def get_rawg_client():
    global _client
    if _client is None:
        api_key = os.environ.get("RAWG_API_KEY")
        if not api_key:
            raise RuntimeError("RAWG_API_KEY environment variable is not set")
        _client = RawgClient(api_key)
    return _client


class RawgClient:

    def __init__(self, api_key):
        self._params = {"key": api_key}

    def _get(self, path, **params):
        response = requests.get(
            f"{BASE_URL}{path}",
            params={**self._params, **params},
        )
        response.raise_for_status()
        return response.json()

    def search_games(self, query, page=1, page_size=20):
        return self._get("/games", search=query, page=page, page_size=page_size)

    def get_game(self, slug_or_id):
        return self._get(f"/games/{slug_or_id}")