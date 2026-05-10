from dataclasses import asdict, dataclass
from typing import Literal


@dataclass
class GameQuery:
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

    ordering: Literal["name", "released", "added", "created", "updated", "rating", "metacritic", "-name", "-released", "-added", "-created", "-updated", "-rating", "-metacritic"] | None = None

    def to_params(self) -> dict:
        data = asdict(self)

        return {k: v for k, v in data.items() if v is not None and v is not False}