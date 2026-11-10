# Playra API

Backend for Playra, a game tracking app. It serves game data from IGDB, and stores users, ratings, wishlists and lists in Supabase. The frontend lives in `playra-frontend`.

## Stack

- Python 3.11
- Pyramid, served with Waitress
- Supabase (Postgres and auth) via `supabase-py`
- IGDB API for game data (via a Twitch developer app access token), with results cached in Supabase
- Pydantic for request and response schemas
- RapidFuzz for scoring id matches in the RAWG→IGDB migration script

## Getting started

Create a `.env` file in the project root:

```
SUPABASE_URL=
SUPABASE_KEY=
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
```

`TWITCH_CLIENT_ID`/`TWITCH_CLIENT_SECRET` come from a free app registered at https://dev.twitch.tv/console/apps — IGDB authenticates via Twitch's OAuth client-credentials flow.

`RAWG_API_KEY` is **not** needed to run the app. It's only needed temporarily, to run `migrate_rawg_ids` (see Scripts below); it can be removed once that migration is verified.

`development.ini` allows CORS from `http://localhost:5173`. To use other origins, set `CORS_ORIGINS` (comma separated).

### With Docker

```sh
just dev
```

This builds the image and runs the server on port 6543 with hot reload.

### Without Docker

```sh
python3 -m venv env
env/bin/pip install -e ".[testing]"
env/bin/pserve development.ini --reload
```

Environment variables are read from the shell, so export them first if you aren't using Docker.

## Commands

| Command          | Description                    |
| ---------------- | ------------------------------ |
| `just dev`       | Run with hot reload            |
| `just run`       | Run the production config      |
| `just lint`      | Run ruff                       |
| `just lint-fix`  | Run ruff with autofix          |
| `just typecheck` | Run mypy                       |
| `just shell`     | Open a shell in the container  |
| `env/bin/pytest` | Run tests (non-Docker setup)   |

## API

All routes are under `/api/v1`. `GET /health` is used for uptime checks.

| Route                              | Description                              |
| ---------------------------------- | ---------------------------------------- |
| `/games`                           | Search and filter games                  |
| `/games/popular`, `/games/recent`  | Popular and newly released games         |
| `/games/{id}`                      | Game details                             |
| `/games/{id}/user`                 | Current user's rating and wishlist state |
| `/games/{id}/screenshots`          | Screenshots                              |
| `/games/{id}/related`              | Franchise (collection) and similar games |
| `/genres`                          | Genre list                               |
| `/lists`, `/lists/public`          | Your lists and public lists              |
| `/lists/{id}`, `/lists/{id}/games` | A list and its games                     |
| `/profile/{user_id}`               | User profile                             |
| `/admin/users`                     | User management (admin only)             |
| `/admin/users/{user_id}/role`      | Change a user's role (admin only)        |

Requests are authenticated with a Supabase access token sent as `Authorization: Bearer <token>`.

### Game data contract

Switching providers (RAWG → IGDB) changed the shape of the games endpoints. If you're working on `playra-frontend`, note:

- **Ids are numeric only.** No slug-or-id lookups — `/games/{id}` etc. take an IGDB integer id.
- **Ratings are 0–100 floats** (`rating`, `aggregated_rating`, `total_rating`), not RAWG's 0–5 scale with a separate `rating_top`.
- **Pagination is `page` / `page_size` / `has_more`** — no `count`/`next`/`previous`. IGDB doesn't give a total count cheaply.
- **`first_release_date` is a unix timestamp**, not an ISO date string.
- **`cover_url` / `screenshot_urls`** are pre-resolved `images.igdb.com` CDN URLs, not `{id, image}` dicts.
- **Age ratings are dropped.** IGDB's rating enum needs a second lookup table to resolve; not implemented yet — this is a known gap, not a bug.
- **`/games/{id}/related`** replaces `/games/{id}/game-series`, returning `{collection_name, collection_games, similar_games}` instead of a flat games list — IGDB's `collection` (franchise) and `similar_games` don't map 1:1 to RAWG's "game series".
- **Adding games to a list** now sends `release_year` (int) and `critic_rating` (float, 0–100) instead of `released` (date) and `metacritic` (int); `background_image` is now `cover_url`.

## Scripts

`migrate_rawg_ids` is a one-off migration run once when switching a database from RAWG ids to IGDB ids (`list_games.game_id` has no provider tag, so existing rows need their ids translated). It never writes anything until `--apply` is passed — see the module docstring in `playra/scripts/migrate_rawg_ids.py` for the full dry-run → review → apply flow.

```sh
env/bin/python -m playra.scripts.migrate_rawg_ids --dry-run
# review mapping_review.csv, fill in the blank igdb_id column, save it
env/bin/python -m playra.scripts.migrate_rawg_ids --apply mapping_auto.csv mapping_review_done.csv
```

It also needs a one-time schema change — see `playra/scripts/schema_changes.sql`.

## Project layout

```
playra/
  auth/       Authentication, authorization and decorators
  clients/    IGDB, Supabase and cache clients
  schemas/    Pydantic models
  scripts/    One-off/maintenance scripts (db init, RAWG->IGDB id migration)
  views/api/  Route handlers (games, lists, profile, admin)
  routes.py   Route definitions
tests/
```

## Deployment

The `Dockerfile` builds an image that runs `production.ini` on port 6543.
