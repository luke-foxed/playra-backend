"""One-off: apply the IGDB rewrite's list_games column renames directly, via a
real Postgres connection -- supabase-py/PostgREST has no way to run DDL
(ALTER TABLE), so this is the one piece of the migration that can't go through
the normal Supabase client.

Renames (and retypes) three list_games columns from their RAWG-shaped names to
the names the backend now writes:
    released          (date)   -> release_year      (integer)
    metacritic         (int)    -> critic_rating      (double precision)
    background_image  (text)   -> cover_url           (text, unchanged type)

Needs a *direct* Postgres connection string -- not SUPABASE_URL/SUPABASE_KEY,
which only reach PostgREST. Get it from:
    Supabase dashboard -> Project Settings -> Database -> Connection string -> URI
(the password there is your database password, set when the project was
created or reset from that same page -- not the SUPABASE_KEY service-role JWT).

Put it in .env as:
    SUPABASE_DB_URL=postgresql://postgres:<password>@<host>:5432/postgres

Usage:
    python -m playra.scripts.apply_schema_changes          # shows the plan, asks to confirm
    python -m playra.scripts.apply_schema_changes --yes    # no confirmation prompt
    python -m playra.scripts.apply_schema_changes --dry-run  # only prints the plan, changes nothing

Safe to re-run: each rename is skipped if the old column is already gone (i.e.
a previous run already applied it), so running it twice does nothing the
second time.
"""
import argparse
import logging
import os
import sys

import psycopg2

log = logging.getLogger(__name__)

TABLE = "list_games"

# (old_column, new_column, type_change_sql_or_None)
RENAMES = [
    ("released", "release_year", "integer USING EXTRACT(YEAR FROM {col})::integer"),
    ("metacritic", "critic_rating", "double precision USING {col}::double precision"),
    ("background_image", "cover_url", None),
]


def _existing_columns(cur) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (TABLE,),
    )
    return {row[0] for row in cur.fetchall()}


def plan(cur) -> list[tuple[str, str, str | None]]:
    """Returns the renames that still need to happen, skipping ones already done."""
    existing = _existing_columns(cur)
    todo = []
    for old, new, retype in RENAMES:
        if new in existing and old not in existing:
            log.info("%s -> %s: already applied, skipping", old, new)
            continue
        if old not in existing:
            log.warning("%s -> %s: neither column exists on %s -- skipping, check the table manually", old, new, TABLE)
            continue
        todo.append((old, new, retype))
    return todo


def apply(cur, todo: list[tuple[str, str, str | None]]) -> None:
    for old, new, retype in todo:
        cur.execute(f'ALTER TABLE {TABLE} RENAME COLUMN "{old}" TO "{new}"')
        log.info("renamed %s -> %s", old, new)
        if retype:
            cur.execute(f'ALTER TABLE {TABLE} ALTER COLUMN "{new}" TYPE {retype.format(col=new)}')
            log.info("retyped %s", new)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", "-y", action="store_true", help="Don't ask for confirmation before applying")
    parser.add_argument("--dry-run", action="store_true", help="Only print the plan; connect read-only, change nothing")
    args = parser.parse_args(argv)

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        log.error("SUPABASE_DB_URL is not set. See this script's module docstring for where to get it.")
        return 1

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            todo = plan(cur)

            if not todo:
                log.info("Nothing to do -- all renames already applied (or no matching columns found).")
                return 0

            log.info("Plan:")
            for old, new, retype in todo:
                log.info("  %s.%s -> %s%s", TABLE, old, new, " (retyped)" if retype else "")

            if args.dry_run:
                log.info("--dry-run: stopping here, nothing changed.")
                return 0

            if not args.yes:
                reply = input(f"\nApply these {len(todo)} change(s) to {TABLE}? [y/N] ").strip().lower()
                if reply != "y":
                    log.info("Aborted, nothing changed.")
                    return 1

            apply(cur, todo)
            conn.commit()
            log.info("Done.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
