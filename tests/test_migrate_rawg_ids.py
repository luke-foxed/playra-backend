from playra.scripts.migrate_rawg_ids import (
    AUTO_ACCEPT_MARGIN,
    AUTO_ACCEPT_SCORE,
    _year_from_unix,
    score_candidate,
)


def _unix_year(year: int) -> int:
    import datetime
    return int(datetime.datetime(year, 6, 1, tzinfo=datetime.UTC).timestamp())


def test_exact_name_and_year_scores_highest():
    candidate = {"name": "Hollow Knight", "first_release_date": _unix_year(2017)}
    score = score_candidate("Hollow Knight", 2017, candidate)
    assert score >= AUTO_ACCEPT_SCORE


def test_year_mismatch_by_more_than_two_is_penalized():
    exact_year = score_candidate("Hollow Knight", 2017, {"name": "Hollow Knight", "first_release_date": _unix_year(2017)})
    far_year = score_candidate("Hollow Knight", 2017, {"name": "Hollow Knight", "first_release_date": _unix_year(2021)})
    assert far_year < exact_year


def test_different_games_with_similar_names_dont_both_score_above_threshold_with_small_margin():
    # Regression guard for the auto-accept margin: two distinctly different titles
    # with similar names should not be indistinguishable to the scorer.
    a = score_candidate("Need for Speed", 2015, {"name": "Need for Speed", "first_release_date": _unix_year(2015)})
    b = score_candidate("Need for Speed", 2015, {"name": "Need for Speed: Heat", "first_release_date": _unix_year(2019)})
    assert a - b >= AUTO_ACCEPT_MARGIN or b < AUTO_ACCEPT_SCORE


def test_no_year_data_falls_back_to_name_only():
    score = score_candidate("Celeste", None, {"name": "Celeste", "first_release_date": None})
    assert score == 100


def test_year_from_unix_roundtrip():
    assert _year_from_unix(_unix_year(2020)) == 2020
    assert _year_from_unix(None) is None
