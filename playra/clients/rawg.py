import os
import re

import requests
from rapidfuzz import fuzz

from playra.clients.cache import cached
from playra.schemas.games import GameQuery, GameResponse, GameScreenshotsResponse, GameSeriesResponse, GamesResponse, GenresResponse

BASE_URL = "https://api.rawg.io/api"

_YEAR_SUFFIX_RE = re.compile(r'-\d{4}$')

def _dedup(games):
    seen = set()
    return [g for g in games if not (g.id in seen or seen.add(g.id))]

_PUNCT_RE = re.compile(r'[^\w\s]')

def _normalize_name(s: str) -> str:
    return ' '.join(_PUNCT_RE.sub(' ', s.lower()).split())

def _rerank(games, query: str):
    q = _normalize_name(query)
    def score(game):
        name = _normalize_name(game.name or "")
        r = fuzz.ratio(q, name)
        # partial_ratio only when name is longer — handles prefix queries ("star wars out" → "star wars outlaws")
        # avoids short names ("nier") scoring 100 against longer queries ("nier automata")
        if len(name) > len(q):
            return max(r, fuzz.partial_ratio(q, name))
        return r
    return sorted(games, key=score, reverse=True)

def _dedup_rich(games):
    # RAWG sometimes lists the same game twice: a canonical entry ("soulcalibur") and a
    # year-suffixed duplicate ("soulcalibur-1998") with sparse data. Group by normalized
    # slug and keep whichever entry has the higher `added` count (more community data).
    best = {}
    for game in games:
        key = _YEAR_SUFFIX_RE.sub('', game.slug)
        if key not in best or game.added > best[key].added:
            best[key] = game
    return list(best.values())
_GAMES_TTL = 60 * 60 * 24        # 24 hours
_GAME_TTL = 60 * 60 * 24 * 7     # 7 days
_GAME_EXTRAS_TTL = 60 * 60 * 24 * 28  # 28 days

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
        if query.search:
            # Drop ordering so RAWG ranks by relevance; overfetch to give reranker more candidates.
            fetch_query = query.model_copy(update={"page_size": min(query.page_size * 2, 40), "ordering": None})
            response = GamesResponse(**self._fetch_games(fetch_query))
            response.results = _rerank(_dedup_rich(response.results), query.search)[:query.page_size]
        else:
            response = GamesResponse(**self._fetch_games(query))
            response.results = _dedup_rich(response.results)
        return response

    @cached(table="game_queries", key_fn=lambda query: {"_list": "popular", **query.to_params()}, ttl_seconds=_GAMES_TTL)
    def _fetch_popular_games(self, query: GameQuery) -> dict:
        return self._get("/games/lists/main", discover=True, ordering="-added", **query.to_params())

    def get_popular_games(self, query: GameQuery) -> GamesResponse:
        # RAWG's lists/main endpoint returns duplicates, so we overfetch (2x, capped at API max of 40)
        # to ensure we have enough unique results to fill the requested page after deduplication.
        fetch_query = query.model_copy(update={"page_size": min(query.page_size * 2, 40)})
        response = GamesResponse(**self._fetch_popular_games(fetch_query))
        response.results = _dedup(response.results)[:query.page_size]
        return response

    @cached(table="game_queries", key_fn=lambda query: {"_list": "recent", **query.to_params()}, ttl_seconds=_GAMES_TTL)
    def _fetch_recent_games(self, query: GameQuery) -> dict:
        return self._get("/games/lists/recent-games-past", discover=True, ordering="-added", **query.to_params())

    def get_recent_games(self, query: GameQuery) -> GamesResponse:
        # Same overfetch + dedup strategy as get_popular_games.
        fetch_query = query.model_copy(update={"page_size": min(query.page_size * 2, 40)})
        response = GamesResponse(**self._fetch_recent_games(fetch_query))
        response.results = _dedup(response.results)[:query.page_size]
        return response

    @cached(table="games", key_fn=lambda slug_or_id: slug_or_id, ttl_seconds=_GAME_TTL)
    def _fetch_game(self, slug_or_id: str) -> dict:
        return self._get(f"/games/{slug_or_id}")

    def get_game(self, slug_or_id: str) -> GameResponse:
        return GameResponse(**self._fetch_game(slug_or_id))

    @cached(table="games", key_fn=lambda slug_or_id: f"{slug_or_id}:screenshots", ttl_seconds=_GAME_EXTRAS_TTL)
    def _fetch_game_screenshots(self, slug_or_id: str) -> dict:
        return self._get(f"/games/{slug_or_id}/screenshots")

    def get_game_screenshots(self, slug_or_id: str) -> GameScreenshotsResponse:
        return GameScreenshotsResponse(**self._fetch_game_screenshots(slug_or_id))

    @cached(table="games", key_fn=lambda slug_or_id: f"{slug_or_id}:series", ttl_seconds=_GAME_EXTRAS_TTL)
    def _fetch_game_series(self, slug_or_id: str) -> dict:
        return self._get(f"/games/{slug_or_id}/game-series")

    def get_game_series(self, slug_or_id: str) -> GameSeriesResponse:
        return GameSeriesResponse(**self._fetch_game_series(slug_or_id))

    @cached(table="game_queries", key_fn=lambda: {"_list": "genres"}, ttl_seconds=_GAME_EXTRAS_TTL)
    def _fetch_genres(self) -> dict:
        return self._get("/genres")

    def get_genres(self) -> GenresResponse:
        return GenresResponse(**self._fetch_genres())


def get_rawg_client(cache_client) -> RawgClient:
    global _client
    if _client is None:
        api_key = os.environ.get("RAWG_API_KEY")
        if not api_key:
            raise RuntimeError("RAWG_API_KEY environment variable is not set")
        _client = RawgClient(api_key, cache_client)
    return _client
