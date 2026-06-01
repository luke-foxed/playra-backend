from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator

BATCH_LIMIT = 50


class ListGameInput(BaseModel):
    game_id: int
    name: str | None = None
    released: date | None = None
    genres: list[dict[str, Any]] | None = None
    metacritic: int | None = None
    background_image: str | None = None
    user_rating: float | None = None


class ListGameEntry(BaseModel):
    game_id: int
    added_at: datetime
    name: str | None = None
    released: date | None = None
    genres: list[dict[str, Any]] | None = None
    metacritic: int | None = None
    background_image: str | None = None
    user_rating: float | None = None


class ListSummaryResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    cover_url: str | None = None
    created_by: str
    is_public: bool
    type: Literal["wishlist", "ratings", "custom"]
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class ListDetailResponse(ListSummaryResponse):
    games: list[ListGameEntry]


class ListRequest(BaseModel):
    name: str
    description: str | None = None
    cover_url: str | None = None
    is_public: bool = False

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError("name cannot be empty")
        return v


class ListGamesAddRequest(BaseModel):
    games: list[ListGameInput]

    @field_validator("games")
    @classmethod
    def limit_batch(cls, v):
        if len(v) > BATCH_LIMIT:
            raise ValueError(f"cannot add more than {BATCH_LIMIT} games at once")
        return v


class ListGamesDeleteRequest(BaseModel):
    game_ids: list[int]

    @field_validator("game_ids")
    @classmethod
    def limit_batch(cls, v):
        if len(v) > BATCH_LIMIT:
            raise ValueError(f"cannot remove more than {BATCH_LIMIT} games at once")
        return v


class ListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    ordering: Literal[
        "name", "created_at", "updated_at",
        "-name", "-created_at", "-updated_at",
    ] | None = None
