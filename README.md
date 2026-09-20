# Playra API

Backend for Playra, a game tracking app. It serves game data from RAWG, and stores users, ratings, wishlists and lists in Supabase. The frontend lives in `playra-frontend`.

## Stack

- Python 3.11
- Pyramid, served with Waitress
- Supabase (Postgres and auth) via `supabase-py`
- RAWG API for game data, with results cached in Supabase
- Pydantic for request and response schemas
- RapidFuzz for re-ranking search results
- Docker and [just](https://github.com/casey/just) for local workflow

## Getting started

Create a `.env` file in the project root:

```
SUPABASE_URL=
SUPABASE_KEY=
RAWG_API_KEY=
```

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
| `/games/{id}/game-series`          | Other games in the series                |
| `/genres`                          | Genre list                               |
| `/lists`, `/lists/public`          | Your lists and public lists              |
| `/lists/{id}`, `/lists/{id}/games` | A list and its games                     |
| `/profile/{user_id}`               | User profile                             |
| `/admin/users`                     | User management (admin only)             |
| `/admin/users/{user_id}/role`      | Change a user's role (admin only)        |

Requests are authenticated with a Supabase access token sent as `Authorization: Bearer <token>`.

## Project layout

```
playra/
  auth/       Authentication, authorization and decorators
  clients/    RAWG, Supabase and cache clients
  schemas/    Pydantic models
  views/api/  Route handlers (games, lists, profile, admin)
  routes.py   Route definitions
tests/
```

## Deployment

The `Dockerfile` builds an image that runs `production.ini` on port 6543.
