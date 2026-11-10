from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# IGDB filter params arrive as query-string values (always strings) but are
# typed as int lists here, so each needs the same "1,2,3" -> [1,2,3] split.
_CSV_INT_FIELDS = ("genres", "platforms", "themes", "game_modes", "player_perspectives")


def _year_start_unix(year: int) -> int:
    return int(datetime(year, 1, 1, tzinfo=UTC).timestamp())


def _year_end_unix(year: int) -> int:
    return int(datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC).timestamp())


class GameSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    slug: str
    name: str
    summary: str | None = None
    first_release_date: int | None = None  # unix timestamp; frontend formats
    cover_url: str | None = None
    genres: list[dict[str, Any]] = []
    platforms: list[dict[str, Any]] = []
    rating: float | None = None             # 0-100, IGDB user rating
    aggregated_rating: float | None = None  # 0-100, critic score (closest analog to Metacritic)
    total_rating: float | None = None       # 0-100, blended user+critic
    total_rating_count: int | None = None
    community_rating: float | None = Field(default=None, exclude=True)
    playra_community_score: float | None = None


class GameResponse(GameSummaryResponse):
    storyline: str | None = None
    developers: list[str] = []
    publishers: list[str] = []
    screenshot_urls: list[str] = []
    artwork_url: str | None = None  # wide hero-banner image; falls back to cover_url if absent
    website: str | None = None
    from_cache: bool = Field(default=False, exclude=True)


class GamesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[GameSummaryResponse]
    page: int
    page_size: int
    has_more: bool  # IGDB doesn't give a cheap total count; inferred from a full page
    from_cache: bool = Field(default=False, exclude=True)


class GameScreenshotsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[str]  # resolved images.igdb.com URLs
    from_cache: bool = Field(default=False, exclude=True)


class GameRelatedResponse(BaseModel):
    """Combines IGDB's `collection` (franchise, e.g. all "Dark Souls" games)
    with `similar_games` (IGDB's own similarity graph) into one related-games view."""

    model_config = ConfigDict(extra="allow")

    collection_name: str | None = None
    collection_games: list[dict[str, Any]] = []
    similar_games: list[dict[str, Any]] = []
    from_cache: bool = Field(default=False, exclude=True)


class GenreResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    slug: str


class GenresResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[GenreResponse]
    from_cache: bool = Field(default=False, exclude=True)


class PlatformResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    abbreviation: str | None = None
    generation: int | None = Field(default=None, exclude=True)


class PlatformsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[PlatformResponse]
    from_cache: bool = Field(default=False, exclude=True)


class GameQuery(BaseModel):
    page: int = 1
    page_size: int = Field(default=20, gt=0, le=40)

    search: str | None = None

    genres: list[int] | None = None
    platforms: list[int] | None = None
    themes: list[int] | None = None
    game_modes: list[int] | None = None
    player_perspectives: list[int] | None = None

    release_year_min: int | None = None
    release_year_max: int | None = None
    rating_min: float | None = None
    rating_max: float | None = None

    ordering: Literal[
        "name", "-name",
        "first_release_date", "-first_release_date",
        "rating", "-rating",
        "total_rating", "-total_rating",
        "total_rating_count", "-total_rating_count",
        "aggregated_rating", "-aggregated_rating",
    ] | None = None

    @field_validator(*_CSV_INT_FIELDS, mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v

    def to_where(self) -> str:
        """Builds an Apicalypse `where` clause body (no leading "where ") from the
        structured filters. Free-text `search` is handled separately by the caller."""
        clauses = []
        for field in ("genres", "platforms", "themes", "game_modes", "player_perspectives"):
            values = getattr(self, field)
            if values:
                clauses.append(f"{field} = ({','.join(str(v) for v in values)})")
        if self.release_year_min is not None:
            clauses.append(f"first_release_date >= {_year_start_unix(self.release_year_min)}")
        if self.release_year_max is not None:
            clauses.append(f"first_release_date <= {_year_end_unix(self.release_year_max)}")
        if self.rating_min is not None:
            clauses.append(f"total_rating >= {self.rating_min}")
        if self.rating_max is not None:
            clauses.append(f"total_rating <= {self.rating_max}")
        return " & ".join(clauses)

    def cache_key(self) -> dict:
        return self.model_dump(exclude_none=True)
