-- Schema changes for the IGDB rewrite. Run by hand in the Supabase SQL editor.
-- There's no migration framework wired to the live DB (alembic in this repo only
-- touches an unused placeholder table), so this is the only record of the change.
--
-- list_games' denormalized snapshot columns were shaped around RAWG's fields.
-- The backend now writes release_year/critic_rating/cover_url instead of
-- released/metacritic/background_image -- rename + retype to match, or every
-- POST /api/v1/lists/{id}/games will fail against the old column names.

ALTER TABLE list_games RENAME COLUMN released TO release_year;
ALTER TABLE list_games ALTER COLUMN release_year TYPE integer USING EXTRACT(YEAR FROM release_year)::integer;

ALTER TABLE list_games RENAME COLUMN metacritic TO critic_rating;
ALTER TABLE list_games ALTER COLUMN critic_rating TYPE double precision USING critic_rating::double precision;

ALTER TABLE list_games RENAME COLUMN background_image TO cover_url;
-- background_image was already text; no type change needed for the rename alone.
