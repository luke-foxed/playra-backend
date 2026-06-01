from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GameSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    slug: str
    name: str
    released: str | None
    tba: bool
    background_image: str | None
    rating: float
    rating_top: int
    ratings: list[dict[str, Any]] = []
    ratings_count: int
    reviews_text_count: int
    added: int
    added_by_status: dict[str, Any] | None
    metacritic: int | None
    playtime: int
    suggestions_count: int
    updated: str
    esrb_rating: dict[str, Any] | None
    platforms: list[dict[str, Any]] | None = None
    community_rating: float | None = Field(default=None, exclude=True)
    playra_community_score: float | None = None


class GameResponse(GameSummaryResponse):
    description: str | None = None
    website: str | None = None
    genres: list[dict[str, Any]] = []
    developers: list[dict[str, Any]] = []
    publishers: list[dict[str, Any]] = []
    from_cache: bool = Field(default=False, exclude=True)


class GamesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int
    next: str | None
    previous: str | None
    results: list[GameSummaryResponse]
    from_cache: bool = Field(default=False, exclude=True)


class GameScreenshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    image: str


class GameScreenshotsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int
    results: list[GameScreenshot]
    from_cache: bool = Field(default=False, exclude=True)


class GameSeriesResponse(GamesResponse):
    pass


class GameQuery(BaseModel):
    # pagination
    page: int = 1
    page_size: int = 20

    # search
    search: str | None = None
    search_precise: bool = False
    search_exact: bool = False

    # filters (generic comma-separated strings)
    parent_platforms: str | None = None
    platforms: str | None = None
    stores: str | None = None

    developers: str | None = None
    publishers: str | None = None
    genres: str | None = None
    tags: str | None = None
    creators: str | None = None

    # date filters
    dates: str | None = None
    updated: str | None = None

    # numeric filters
    platforms_count: int | None = None
    metacritic: str | None = None

    # exclusions
    exclude_collection: int | None = None
    exclude_additions: bool = False
    exclude_parents: bool = False
    exclude_game_series: bool = False
    exclude_stores: str | None = None

    ordering: Literal[
        "name", "released", "added", "created", "updated", "rating", "metacritic",
        "-name", "-released", "-added", "-created", "-updated", "-rating", "-metacritic",
    ] | None = None

    def to_params(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None and v is not False}
