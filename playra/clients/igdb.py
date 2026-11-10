import logging
import os
import threading
import time
from datetime import UTC, datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from playra.clients.cache import cached
from playra.schemas.games import (
    GameQuery,
    GameRelatedResponse,
    GameResponse,
    GameScreenshotsResponse,
    GamesResponse,
    GameSummaryResponse,
    GenreResponse,
    GenresResponse,
)

log = logging.getLogger(__name__)

BASE_URL = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# IGDB covers/screenshots are addressed by opaque image_id and resolved against this CDN.
_IMAGE_BASE = "https://images.igdb.com/igdb/image/upload"

# (connect, read).
_TIMEOUT = (3.05, 10)

# IGDB/Twitch throw transient 5xx under load; retry those and connection errors.
_RETRY_STATUSES = (429, 500, 502, 503, 504)

# IGDB's free tier caps requests at 4/s. Playra's page loads can fire popular+recent+
# games back-to-back, so this is a real budget, not a theoretical one.
_RATE_LIMIT_PER_SECOND = 4.0

_GAMES_TTL = 60 * 60 * 24            # 24 hours
_GAME_TTL = 60 * 60 * 24 * 7         # 7 days
_GAME_EXTRAS_TTL = 60 * 60 * 24 * 28  # 28 days

# IGDB omits a field from its JSON entirely when it equals that field's numeric
# default -- and `category`'s default is 0 (main_game), the single most common
# value. So `where category = 0` (or `!= null`) matches nothing: IGDB's query
# engine treats those omitted-default rows as unset, not as literally 0. The
# only way to keep "main game" filtering is to exclude the *other* categories by
# name instead of matching the default: dlc_addon(1), expansion(2), bundle(3),
# mod(5), episode(6), season(7), pack(13), update(14). Confirmed empirically
# against the live API -- this isn't documented anywhere obvious.
_EXCLUDE_NON_GAME_CATEGORIES = "category != 1 & category != 2 & category != 3 & category != 5 & category != 6 & category != 7 & category != 13 & category != 14"

_GAME_FIELDS = (
    "id,name,slug,summary,storyline,first_release_date,"
    "cover.image_id,"
    "genres.id,genres.name,"
    "platforms.id,platforms.name,platforms.abbreviation,"
    "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
    "rating,aggregated_rating,total_rating,total_rating_count,hypes,"
    "screenshots.image_id,"
    "similar_games,"
    "collection.id,collection.name,"
    "websites.url,websites.category,"
    "category"
)


class IgdbHTTPError(requests.HTTPError):
    """IGDB returned an error status. Message is scrubbed of the client secret/token.

    Subclasses HTTPError so callers can keep inspecting `response.status_code`.
    """


class IgdbUnavailableError(requests.RequestException):
    """IGDB (or the Twitch token endpoint) could not be reached at all."""


class IgdbNotFoundError(Exception):
    """IGDB has no REST 404 — a bad id just returns `200 []`. Raised explicitly
    by callers that need "not found" semantics (e.g. get_game)."""


def _build_session() -> requests.Session:
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=_RETRY_STATUSES,
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _scrub(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _escape_search(term: str) -> str:
    return term.replace("\\", "\\\\").replace('"', '\\"')


def _sort_clause(ordering: str) -> str:
    desc = ordering.startswith("-")
    field = ordering.lstrip("-")
    return f"{field} {'desc' if desc else 'asc'}"


def _image_url(image_id: str | None, size: str = "t_cover_big") -> str | None:
    return f"{_IMAGE_BASE}/{size}/{image_id}.jpg" if image_id else None


def _normalize_game(row: dict) -> dict:
    cover = row.get("cover") or {}
    involved = row.get("involved_companies") or []
    developers = [ic["company"]["name"] for ic in involved if ic.get("developer") and ic.get("company")]
    publishers = [ic["company"]["name"] for ic in involved if ic.get("publisher") and ic.get("company")]
    # category 1 = "official" per IGDB's website-category enum.
    website = next((w["url"] for w in row.get("websites") or [] if w.get("category") == 1), None)

    return {
        "id": row["id"],
        "slug": row.get("slug", ""),
        "name": row.get("name", ""),
        "summary": row.get("summary"),
        "storyline": row.get("storyline"),
        "first_release_date": row.get("first_release_date"),
        "cover_url": _image_url(cover.get("image_id")),
        "genres": [{"id": g["id"], "name": g["name"]} for g in row.get("genres") or []],
        "platforms": [
            {"id": p["id"], "name": p["name"], "abbreviation": p.get("abbreviation")}
            for p in row.get("platforms") or []
        ],
        "rating": row.get("rating"),
        "aggregated_rating": row.get("aggregated_rating"),
        "total_rating": row.get("total_rating"),
        "total_rating_count": row.get("total_rating_count"),
        "developers": developers,
        "publishers": publishers,
        "screenshot_urls": [
            _image_url(s["image_id"], size="t_screenshot_big")
            for s in row.get("screenshots") or []
            if s.get("image_id")
        ],
        "website": website,
    }


class _TokenManager:
    """Caches a Twitch app-access-token in memory, refreshing before it expires.

    Twitch app tokens last ~60 days, so lock contention here is irrelevant — the
    lock just stops concurrent waitress threads from all refetching at once.
    """

    def __init__(self, client_id: str, client_secret: str, session: requests.Session):
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: datetime = datetime.min.replace(tzinfo=UTC)

    def get_token(self) -> str:
        with self._lock:
            if self._token is None or datetime.now(UTC) >= self._expires_at:
                self._fetch_token()
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None

    def current_token(self) -> str | None:
        return self._token

    def _fetch_token(self) -> None:
        try:
            response = self._session.post(
                TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise IgdbUnavailableError(
                f"Twitch OAuth token request failed: {_scrub(str(e), self._client_secret)}"
            ) from None
        except ValueError as e:
            raise IgdbUnavailableError(f"Twitch OAuth token response was not JSON: {e}") from None

        self._token = data["access_token"]
        # Refresh 60s early so a request mid-flight never hits an expired token.
        self._expires_at = datetime.now(UTC) + timedelta(seconds=max(data.get("expires_in", 0) - 60, 0))


class _RateLimiter:
    """Spaces calls at least 1/max_per_second apart. Sits below the cache layer
    inside `_post`, so a cache hit never pays the throttle cost."""

    def __init__(self, max_per_second: float = _RATE_LIMIT_PER_SECOND):
        self._min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._min_interval - (now - self._last_call)
            if delay > 0:
                time.sleep(delay)
            self._last_call = time.monotonic()


class IgdbClient:

    def __init__(self, client_id: str, client_secret: str, cache_client):
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache = cache_client
        self._session = _build_session()
        self._tokens = _TokenManager(client_id, client_secret, self._session)
        self._rate_limiter = _RateLimiter()

    def _scrub(self, text: str) -> str:
        return _scrub(text, self._client_secret, self._tokens.current_token() or "")

    def _post(self, endpoint: str, apicalypse_query: str) -> list[dict]:
        self._rate_limiter.wait()
        token = self._tokens.get_token()
        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain",
        }
        url = f"{BASE_URL}/{endpoint}"

        try:
            response = self._session.post(url, data=apicalypse_query.encode(), headers=headers, timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise IgdbUnavailableError(f"IGDB request to {endpoint} failed: {self._scrub(str(e))}") from None

        if response.status_code == 401:
            # Surprise expiry/revocation — refresh once and retry, rather than
            # waiting for the next scheduled refresh to notice.
            self._tokens.invalidate()
            headers["Authorization"] = f"Bearer {self._tokens.get_token()}"
            try:
                response = self._session.post(url, data=apicalypse_query.encode(), headers=headers, timeout=_TIMEOUT)
            except requests.RequestException as e:
                raise IgdbUnavailableError(f"IGDB request to {endpoint} failed: {self._scrub(str(e))}") from None

        if not response.ok:
            raise IgdbHTTPError(
                f"IGDB returned {response.status_code} for {endpoint}: {self._scrub(response.text[:200])}",
                response=response,
            )

        try:
            return response.json()
        except ValueError as e:
            raise IgdbUnavailableError(f"IGDB returned non-JSON for {endpoint}: {self._scrub(str(e))}") from None

    # _fetch_* methods are the cache boundary. IGDB endpoints return bare JSON
    # arrays, but the `cached()` decorator spreads its result with `**result` —
    # which crashes on a list — so every _fetch_* wraps its rows as {"rows": [...]}.
    # get_* methods are the public API — always return typed models.

    @cached(table="game_queries", key_fn=lambda query: {"igdb": "games", **query.cache_key()}, ttl_seconds=_GAMES_TTL)
    def _fetch_games(self, query: GameQuery) -> dict:
        clauses = [_EXCLUDE_NON_GAME_CATEGORIES]
        where = query.to_where()
        if where:
            clauses.append(where)

        parts = []
        if query.search:
            parts.append(f'search "{_escape_search(query.search)}";')
        parts.append(f"fields {_GAME_FIELDS};")
        parts.append(f"where {' & '.join(clauses)};")
        if query.ordering and not query.search:
            # IGDB ignores an explicit `sort` when `search` is present — it ranks
            # by relevance instead. Matches RAWG's old "drop ordering on search" rule.
            parts.append(f"sort {_sort_clause(query.ordering)};")
        parts.append(f"limit {query.page_size};")
        parts.append(f"offset {(query.page - 1) * query.page_size};")

        rows = self._post("games", "".join(parts))
        return {"rows": rows}

    def get_games(self, query: GameQuery) -> GamesResponse:
        cached_result = self._fetch_games(query)
        rows = cached_result["rows"]
        return GamesResponse(
            results=[GameSummaryResponse(**_normalize_game(r)) for r in rows],
            page=query.page,
            page_size=query.page_size,
            has_more=len(rows) == query.page_size,
            from_cache=cached_result.get("from_cache", False),
        )

    @cached(table="game_queries", key_fn=lambda query: {"igdb_list": "popular", **query.cache_key()}, ttl_seconds=_GAMES_TTL)
    def _fetch_popular_games(self, query: GameQuery) -> dict:
        now = int(datetime.now(UTC).timestamp())
        clauses = [
            _EXCLUDE_NON_GAME_CATEGORIES,
            f"first_release_date <= {now}",
            "total_rating_count != null",
        ]
        where = query.to_where()
        if where:
            clauses.append(where)

        apicalypse = (
            f"fields {_GAME_FIELDS};"
            f"where {' & '.join(clauses)};"
            "sort total_rating_count desc;"
            f"limit {query.page_size};"
            f"offset {(query.page - 1) * query.page_size};"
        )
        rows = self._post("games", apicalypse)
        return {"rows": rows}

    def get_popular_games(self, query: GameQuery) -> GamesResponse:
        cached_result = self._fetch_popular_games(query)
        rows = cached_result["rows"]
        return GamesResponse(
            results=[GameSummaryResponse(**_normalize_game(r)) for r in rows],
            page=query.page,
            page_size=query.page_size,
            has_more=len(rows) == query.page_size,
            from_cache=cached_result.get("from_cache", False),
        )

    @cached(table="game_queries", key_fn=lambda query: {"igdb_list": "recent", **query.cache_key()}, ttl_seconds=_GAMES_TTL)
    def _fetch_recent_games(self, query: GameQuery) -> dict:
        now = int(datetime.now(UTC).timestamp())
        thirty_days_ago = now - 30 * 86400
        clauses = [
            _EXCLUDE_NON_GAME_CATEGORIES,
            f"first_release_date <= {now}",
            f"first_release_date > {thirty_days_ago}",
        ]
        where = query.to_where()
        if where:
            clauses.append(where)

        apicalypse = (
            f"fields {_GAME_FIELDS};"
            f"where {' & '.join(clauses)};"
            "sort first_release_date desc;"
            f"limit {query.page_size};"
            f"offset {(query.page - 1) * query.page_size};"
        )
        rows = self._post("games", apicalypse)
        return {"rows": rows}

    def get_recent_games(self, query: GameQuery) -> GamesResponse:
        cached_result = self._fetch_recent_games(query)
        rows = cached_result["rows"]
        return GamesResponse(
            results=[GameSummaryResponse(**_normalize_game(r)) for r in rows],
            page=query.page,
            page_size=query.page_size,
            has_more=len(rows) == query.page_size,
            from_cache=cached_result.get("from_cache", False),
        )

    @cached(table="games", key_fn=lambda igdb_id: f"igdb:{igdb_id}", ttl_seconds=_GAME_TTL)
    def _fetch_game(self, igdb_id: int) -> dict:
        rows = self._post("games", f"fields {_GAME_FIELDS}; where id = {igdb_id};")
        return {"rows": rows}

    def get_game(self, igdb_id: int) -> GameResponse:
        cached_result = self._fetch_game(igdb_id)
        rows = cached_result["rows"]
        if not rows:
            raise IgdbNotFoundError(f"No IGDB game with id {igdb_id}")
        game = GameResponse(**_normalize_game(rows[0]))
        game.from_cache = cached_result.get("from_cache", False)
        return game

    @cached(table="games", key_fn=lambda igdb_id: f"igdb:{igdb_id}:screenshots", ttl_seconds=_GAME_EXTRAS_TTL)
    def _fetch_game_screenshots(self, igdb_id: int) -> dict:
        rows = self._post("screenshots", f"fields image_id; where game = {igdb_id}; limit 50;")
        return {"rows": rows}

    def get_game_screenshots(self, igdb_id: int) -> GameScreenshotsResponse:
        cached_result = self._fetch_game_screenshots(igdb_id)
        urls = [
            _image_url(r["image_id"], size="t_screenshot_big")
            for r in cached_result["rows"]
            if r.get("image_id")
        ]
        return GameScreenshotsResponse(results=urls, from_cache=cached_result.get("from_cache", False))

    @cached(table="games", key_fn=lambda igdb_id: f"igdb:{igdb_id}:related", ttl_seconds=_GAME_EXTRAS_TTL)
    def _fetch_game_related(self, igdb_id: int) -> dict:
        # Can't do this in one Apicalypse call — the collection id and similar-game
        # ids aren't known until the base game is fetched, and IGDB's /multiquery
        # can't template on a prior sub-query's result. Cached as one combined
        # entry so repeat requests only pay this 2-3x round trip cost once.
        base_rows = self._post(
            "games",
            f"fields collection.id,collection.name,similar_games; where id = {igdb_id};",
        )
        if not base_rows:
            raise IgdbNotFoundError(f"No IGDB game with id {igdb_id}")
        base = base_rows[0]

        collection_name = None
        collection_games = []
        collection = base.get("collection")
        if collection:
            coll_rows = self._post(
                "collections",
                "fields games.id,games.name,games.slug,games.cover.image_id,games.first_release_date;"
                f" where id = {collection['id']};",
            )
            if coll_rows:
                collection_name = collection.get("name")
                collection_games = [
                    {
                        "id": g["id"],
                        "name": g.get("name"),
                        "slug": g.get("slug"),
                        "cover_url": _image_url((g.get("cover") or {}).get("image_id")),
                        "first_release_date": g.get("first_release_date"),
                    }
                    for g in (coll_rows[0].get("games") or [])
                    if g.get("id") != igdb_id
                ]

        similar_games = []
        similar_ids = (base.get("similar_games") or [])[:10]
        if similar_ids:
            ids_clause = ",".join(str(i) for i in similar_ids)
            sim_rows = self._post(
                "games",
                f"fields id,name,slug,cover.image_id,first_release_date,total_rating; where id = ({ids_clause});",
            )
            similar_games = [
                {
                    "id": g["id"],
                    "name": g.get("name"),
                    "slug": g.get("slug"),
                    "cover_url": _image_url((g.get("cover") or {}).get("image_id")),
                    "first_release_date": g.get("first_release_date"),
                    "total_rating": g.get("total_rating"),
                }
                for g in sim_rows
            ]

        return {
            "collection_name": collection_name,
            "collection_games": collection_games,
            "similar_games": similar_games,
        }

    def get_game_related(self, igdb_id: int) -> GameRelatedResponse:
        cached_result = self._fetch_game_related(igdb_id)
        return GameRelatedResponse(
            collection_name=cached_result["collection_name"],
            collection_games=cached_result["collection_games"],
            similar_games=cached_result["similar_games"],
            from_cache=cached_result.get("from_cache", False),
        )

    @cached(table="game_queries", key_fn=lambda: {"igdb_list": "genres"}, ttl_seconds=_GAME_EXTRAS_TTL)
    def _fetch_genres(self) -> dict:
        rows = self._post("genres", "fields id,name,slug; sort name asc; limit 50;")
        return {"rows": rows}

    def get_genres(self) -> GenresResponse:
        cached_result = self._fetch_genres()
        genres = [GenreResponse(**r) for r in cached_result["rows"]]
        return GenresResponse(results=genres, from_cache=cached_result.get("from_cache", False))

    def search_raw(self, name: str, limit: int = 10) -> list[dict]:
        """Uncached — used by the one-off id-migration script, which runs a batch
        of throwaway matching queries that shouldn't pollute the response cache."""
        query = f'search "{_escape_search(name)}"; fields id,name,slug,first_release_date; limit {limit};'
        return self._post("games", query)


_client = None


def get_igdb_client(cache_client) -> IgdbClient:
    global _client
    if _client is None:
        client_id = os.environ.get("TWITCH_CLIENT_ID")
        client_secret = os.environ.get("TWITCH_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET environment variables are not set")
        _client = IgdbClient(client_id, client_secret, cache_client)
    return _client
