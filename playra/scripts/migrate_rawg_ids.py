"""One-off migration: translate RAWG ids in `list_games.game_id` to IGDB ids.

Usage:
    python -m playra.scripts.migrate_rawg_ids --dry-run
    python -m playra.scripts.migrate_rawg_ids --apply mapping_auto.csv mapping_review_done.csv

`--dry-run` only SELECTs from Supabase and only makes read-only calls to RAWG and
IGDB -- it never calls .update()/.insert()/.delete(). That makes it safe to run
directly against production to generate the review report before anything is
actually changed.

Flow:
    1. `--dry-run` reads every distinct `game_id` in `list_games`, looks each one
       up on RAWG, searches IGDB for name matches, and scores the candidates.
       High-confidence matches go to mapping_auto.csv (ready to apply as-is).
       Everything else -- no RAWG data, no IGDB candidates, or an ambiguous/low
       score -- goes to mapping_review.csv with a blank `igdb_id` column and the
       top candidates listed, for a human to fill in. Nothing ambiguous is ever
       auto-applied.
    2. Fill in mapping_review.csv's `igdb_id` column by hand (e.g. save as
       mapping_review_done.csv).
    3. `--apply mapping_auto.csv mapping_review_done.csv` rewrites
       list_games.game_id for every row with a filled-in igdb_id. Idempotent via
       a local state file -- rerunning skips ids already migrated. Rows whose
       target id would collide with an existing row in the same list are skipped
       and logged to conflicts.csv instead of applied.
"""
import argparse
import csv
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests
from rapidfuzz import fuzz

from playra.clients.cache import CacheClient
from playra.clients.igdb import get_igdb_client
from playra.clients.supabase import get_supabase_client

log = logging.getLogger(__name__)

RAWG_API_KEY_ENV = "RAWG_API_KEY"
RAWG_BASE_URL = "https://api.rawg.io/api"

DEFAULT_STATE_FILE = Path(__file__).with_name("migrate_rawg_ids_state.json")
DEFAULT_AUTO_CSV = Path("mapping_auto.csv")
DEFAULT_REVIEW_CSV = Path("mapping_review.csv")
DEFAULT_CONFLICTS_CSV = Path("conflicts.csv")

# 90+ on normalized-name ratio reliably means "same title, maybe edition/subtitle
# differences". The margin guards against two distinctly different games with
# similar names (e.g. "Need for Speed" vs "Need for Speed: Heat") both scoring
# high -- those must go to manual review, not be silently resolved.
AUTO_ACCEPT_SCORE = 90
AUTO_ACCEPT_MARGIN = 8
CANDIDATE_COUNT = 5

_PUNCT_RE = re.compile(r'[^\w\s]')


def _normalize_name(s: str) -> str:
    return ' '.join(_PUNCT_RE.sub(' ', (s or "").lower()).split())


def _year_from_iso_date(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _year_from_unix(ts: int | None) -> int | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).year


def fetch_rawg_game(session: requests.Session, rawg_id: int, api_key: str) -> dict | None:
    """Minimal, standalone RAWG lookup. This runs a few hundred one-off requests,
    not a live request path, so it skips the retry/cache sophistication the old
    rawg.py client had (that module is gone, replaced by the IGDB client)."""
    try:
        resp = session.get(f"{RAWG_BASE_URL}/games/{rawg_id}", params={"key": api_key}, timeout=(3.05, 10))
    except requests.RequestException as e:
        log.warning("RAWG lookup failed for id %s: %s", rawg_id, e)
        return None
    if resp.status_code == 404:
        return None
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        log.warning("RAWG lookup failed for id %s: %s", rawg_id, e)
        return None
    return resp.json()


def score_candidate(rawg_name: str, rawg_year: int | None, candidate: dict) -> int:
    """Pure and deterministic -- directly gates auto-accept vs. manual review."""
    name_score = fuzz.ratio(_normalize_name(rawg_name), _normalize_name(candidate.get("name", "")))

    candidate_year = _year_from_unix(candidate.get("first_release_date"))
    bonus = 0
    if rawg_year is not None and candidate_year is not None:
        diff = abs(rawg_year - candidate_year)
        if diff == 0:
            bonus = 10
        elif diff == 1:
            bonus = 5
        elif diff > 2:
            bonus = -15

    return max(0, min(100, round(name_score + bonus)))


def _distinct_rawg_ids(supabase) -> list[int]:
    rows = supabase.table("list_games").select("game_id").execute().data
    return sorted({r["game_id"] for r in rows})


def _load_state(state_file: Path) -> dict:
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"migrated": {}}


def _save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True))


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _review_fieldnames(candidates: int) -> list[str]:
    fields = ["rawg_id", "rawg_name", "rawg_release_year"]
    for i in range(1, candidates + 1):
        fields += [f"candidate_{i}_igdb_id", f"candidate_{i}_name", f"candidate_{i}_year", f"candidate_{i}_score"]
    fields += ["igdb_id", "notes"]
    return fields


def _review_row(rawg_id: int, rawg_name: str, rawg_year: int | None, scored: list[tuple[dict, int]], candidates: int, note: str) -> dict:
    row = {
        "rawg_id": rawg_id,
        "rawg_name": rawg_name,
        "rawg_release_year": rawg_year or "",
        "igdb_id": "",
        "notes": note,
    }
    for i in range(1, candidates + 1):
        if i <= len(scored):
            candidate, score = scored[i - 1]
            row[f"candidate_{i}_igdb_id"] = candidate["id"]
            row[f"candidate_{i}_name"] = candidate.get("name", "")
            row[f"candidate_{i}_year"] = _year_from_unix(candidate.get("first_release_date")) or ""
            row[f"candidate_{i}_score"] = score
        else:
            row[f"candidate_{i}_igdb_id"] = row[f"candidate_{i}_name"] = row[f"candidate_{i}_year"] = row[f"candidate_{i}_score"] = ""
    return row


def run_dry_run(
    auto_csv: Path, review_csv: Path, threshold_auto: int, threshold_margin: int, candidates: int, state_file: Path,
) -> None:
    rawg_api_key = os.environ.get(RAWG_API_KEY_ENV)
    if not rawg_api_key:
        raise RuntimeError(f"{RAWG_API_KEY_ENV} environment variable is not set (needed temporarily for this script)")

    supabase = get_supabase_client()
    cache_client = CacheClient(supabase)
    igdb = get_igdb_client(cache_client)
    rawg_session = requests.Session()

    state = _load_state(state_file)
    already_migrated = set(state.get("migrated", {}).keys())

    rawg_ids = _distinct_rawg_ids(supabase)
    log.info("Found %d distinct game_id value(s) in list_games", len(rawg_ids))

    auto_rows: list[dict] = []
    review_rows: list[dict] = []

    for rawg_id in rawg_ids:
        if str(rawg_id) in already_migrated:
            continue

        rawg_game = fetch_rawg_game(rawg_session, rawg_id, rawg_api_key)
        if rawg_game is None:
            review_rows.append(_review_row(rawg_id, "", None, [], candidates, "no RAWG data found (404 or request failed)"))
            continue

        rawg_name = rawg_game.get("name", "")
        rawg_year = _year_from_iso_date(rawg_game.get("released"))

        try:
            raw_candidates = igdb.search_raw(rawg_name, limit=candidates)
        except Exception as e:
            log.warning("IGDB search failed for RAWG id %s (%s): %s", rawg_id, rawg_name, e)
            raw_candidates = []

        scored = sorted(
            ((c, score_candidate(rawg_name, rawg_year, c)) for c in raw_candidates),
            key=lambda pair: pair[1],
            reverse=True,
        )

        if not scored:
            review_rows.append(_review_row(rawg_id, rawg_name, rawg_year, [], candidates, "no IGDB candidates found"))
            continue

        top_candidate, top_score = scored[0]
        margin = top_score - (scored[1][1] if len(scored) > 1 else 0)

        if top_score >= threshold_auto and margin >= threshold_margin:
            auto_rows.append({
                "rawg_id": rawg_id,
                "rawg_name": rawg_name,
                "rawg_release_year": rawg_year or "",
                "igdb_id": top_candidate["id"],
                "igdb_name": top_candidate.get("name", ""),
                "igdb_release_year": _year_from_unix(top_candidate.get("first_release_date")) or "",
                "score": top_score,
                "margin": margin,
            })
        else:
            note = f"low confidence or ambiguous (top score {top_score}, margin {margin})"
            review_rows.append(_review_row(rawg_id, rawg_name, rawg_year, scored, candidates, note))

    _write_csv(auto_csv, auto_rows, ["rawg_id", "rawg_name", "rawg_release_year", "igdb_id", "igdb_name", "igdb_release_year", "score", "margin"])
    _write_csv(review_csv, review_rows, _review_fieldnames(candidates))

    log.info("Auto-accepted: %d -> %s", len(auto_rows), auto_csv)
    log.info("Needs manual review: %d -> %s", len(review_rows), review_csv)


def _has_conflict(supabase, rawg_id: int, igdb_id: int) -> bool:
    """True if any list already holds both the old (rawg_id) and new (igdb_id)
    game_id. add_games_to_list's upsert implies a unique (list_id, game_id)
    constraint, so rewriting rawg_id -> igdb_id there would collide."""
    rawg_lists = {r["list_id"] for r in supabase.table("list_games").select("list_id").eq("game_id", rawg_id).execute().data}
    if not rawg_lists:
        return False
    igdb_lists = {r["list_id"] for r in supabase.table("list_games").select("list_id").eq("game_id", igdb_id).execute().data}
    return bool(rawg_lists & igdb_lists)


def run_apply(mapping_files: list[Path], state_file: Path, conflicts_csv: Path) -> None:
    supabase = get_supabase_client()
    state = _load_state(state_file)
    migrated = state.setdefault("migrated", {})

    mappings: list[tuple[int, int]] = []
    for path in mapping_files:
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                rawg_id = (row.get("rawg_id") or "").strip()
                igdb_id = (row.get("igdb_id") or "").strip()
                if not rawg_id or not igdb_id:
                    continue
                mappings.append((int(rawg_id), int(igdb_id)))

    conflicts: list[dict] = []
    applied = 0
    skipped_already = 0

    for rawg_id, igdb_id in mappings:
        if str(rawg_id) in migrated:
            skipped_already += 1
            continue

        if _has_conflict(supabase, rawg_id, igdb_id):
            conflicts.append({"rawg_id": rawg_id, "igdb_id": igdb_id, "reason": "target igdb_id already exists in the same list(s) as rawg_id"})
            continue

        row_count = len(supabase.table("list_games").select("list_id").eq("game_id", rawg_id).execute().data)
        supabase.table("list_games").update({"game_id": igdb_id}).eq("game_id", rawg_id).execute()

        log.info("Migrated game_id %s -> %s (%d row(s))", rawg_id, igdb_id, row_count)
        migrated[str(rawg_id)] = igdb_id
        applied += 1

    _save_state(state_file, state)
    if conflicts:
        _write_csv(conflicts_csv, conflicts, ["rawg_id", "igdb_id", "reason"])
        log.warning("%d conflict(s) skipped -> %s", len(conflicts), conflicts_csv)

    log.info("Applied %d mapping(s), skipped %d already-migrated, %d conflict(s)", applied, skipped_already, len(conflicts))


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read-only: generate mapping_auto.csv and mapping_review.csv")
    mode.add_argument("--apply", nargs="+", metavar="MAPPING_CSV", help="Apply one or more completed mapping CSVs (each needs rawg_id,igdb_id columns)")

    parser.add_argument("--threshold-auto", type=int, default=AUTO_ACCEPT_SCORE)
    parser.add_argument("--threshold-margin", type=int, default=AUTO_ACCEPT_MARGIN)
    parser.add_argument("--candidates", type=int, default=CANDIDATE_COUNT)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--auto-csv", type=Path, default=DEFAULT_AUTO_CSV)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument("--conflicts-csv", type=Path, default=DEFAULT_CONFLICTS_CSV)

    args = parser.parse_args(argv)

    if args.dry_run:
        run_dry_run(args.auto_csv, args.review_csv, args.threshold_auto, args.threshold_margin, args.candidates, args.state_file)
    else:
        run_apply([Path(p) for p in args.apply], args.state_file, args.conflicts_csv)

    return 0


if __name__ == "__main__":
    sys.exit(main())
