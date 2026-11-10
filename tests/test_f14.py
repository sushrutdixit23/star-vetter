"""Offline tests for f14_novelty_extra.py: no network. VizieR responses are built
locally as VOTable XML. The point of most tests is the fail-closed rule: an
error, a missing table or a wrong schema must never become 'no match'."""

import io
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import f14_novelty_extra as f14  # noqa: E402

ZTF = f14.CATALOG_BY_KEY["ztf"]
KELT = f14.CATALOG_BY_KEY["kelt"]
ASAS = f14.CATALOG_BY_KEY["asas"]


def votable(cat, rows, with_sep=True, drop=()):
    """VOTable bytes with the columns the catalog needs. rows: list of dicts
    with keys sep, per (list matching per_cols, None = masked), cls, id, tic."""
    from astropy.io.votable import from_table
    from astropy.table import MaskedColumn, Table

    t = Table()
    n = len(rows)
    if with_sep:
        t["_r"] = np.array([r["sep"] for r in rows], float) if n else np.zeros(0)
    t["_RAJ2000"] = np.array([r.get("ra", 10.0) for r in rows], float) if n else np.zeros(0)
    t["_DEJ2000"] = np.array([r.get("dec", 20.0) for r in rows], float) if n else np.zeros(0)
    for i, col in enumerate(cat["per_cols"]):
        vals = [(r["per"][i] if r.get("per") else None) for r in rows]
        t[col] = MaskedColumn([np.nan if v is None else v for v in vals],
                              mask=[v is None for v in vals], dtype=float)
    if cat["class_col"]:
        t[cat["class_col"]] = np.array([r.get("cls", "") for r in rows], dtype="U12") if n \
            else np.array([], dtype="U12")
    t[cat["id_col"]] = np.array([r.get("id", "X") for r in rows], dtype="U20") if n \
        else np.array([], dtype="U20")
    if cat["tic_col"]:
        t[cat["tic_col"]] = np.array([r.get("tic", 0) for r in rows], dtype="i8") if n \
            else np.array([], dtype="i8")
    for c in drop:
        t.remove_column(c)
    buf = io.BytesIO()
    from_table(t).to_xml(buf)
    return buf.getvalue()


ERROR_DOC = b"""<?xml version="1.0"?><VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
<INFO ID="Error" name="Error" value="Table or Catalog not found: J/XX/999/nothere"/>
<RESOURCE></RESOURCE></VOTABLE>"""
BAD_COORD_DOC = b"""<?xml version="1.0"?><VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
<RESOURCE></RESOURCE>
<INFO name="Error" value="Bad Dec(lat): in: 215.54202+-84.44295"/>
<INFO name="QUERY_STATUS" value="ERROR">Bad Dec(lat)</INFO></VOTABLE>"""


# ------------------------------------------------------------ parse / fail closed

def test_error_document_is_an_error_not_zero_rows():
    for doc in (ERROR_DOC, BAD_COORD_DOC):
        with pytest.raises(f14.CatalogError):
            f14.parse_response(doc, ZTF)


def test_table_accompanied_by_an_error_element_is_not_trusted():
    """A partial or truncated answer: rows present AND the server flagged an error."""
    good = votable(ZTF, [{"sep": 1.0, "per": [2.0, None, None], "cls": "EW", "id": "A"}])
    tainted = good.replace(b"<RESOURCE", b'<INFO name="Error" value="query timed out"/><RESOURCE', 1)
    assert tainted != good
    with pytest.raises(f14.CatalogError, match="error"):
        f14.parse_response(tainted, ZTF)
    # same bytes without the error element parse fine, so the test is about the error
    assert len(f14.parse_response(good, ZTF)) == 1


def test_response_without_a_table_is_an_error():
    with pytest.raises(f14.CatalogError):
        f14.parse_response(b"<VOTABLE><RESOURCE></RESOURCE></VOTABLE>", ZTF)


def test_garbage_is_an_error():
    with pytest.raises(f14.CatalogError):
        f14.parse_response(b"<html>503 Service Unavailable</html>", ZTF)


def test_empty_table_with_correct_schema_is_a_verified_empty_result():
    assert f14.parse_response(votable(ZTF, []), ZTF) == []


def test_empty_table_with_wrong_schema_is_not_believed():
    for missing in ("Per", "_r", "Type"):
        with pytest.raises(f14.CatalogError, match="missing"):
            f14.parse_response(votable(ZTF, [], drop=(missing,)), ZTF)


def test_rows_parse_and_masked_periods_are_dropped():
    raw = votable(ZTF, [{"sep": 1.5, "per": [2.0, None, 4.0], "cls": "EW", "id": "ZTFJ1"},
                        {"sep": 9.0, "per": [None, None, None], "cls": "", "id": "ZTFJ2"}])
    rows = f14.parse_response(raw, ZTF)
    assert rows[0]["periods"] == [2.0, 4.0] and rows[0]["cls"] == "EW"
    assert rows[0]["source_id"] == "ZTFJ1" and rows[0]["sep_arcsec"] == pytest.approx(1.5)
    assert rows[1]["periods"] == []


def test_first_row_query_does_not_need_a_separation_column():
    raw = votable(ZTF, [{"sep": 0, "per": [1.0, 1.0, 1.0]}], with_sep=False)
    assert len(f14.parse_response(raw, ZTF, need_sep=False)) == 1
    with pytest.raises(f14.CatalogError):
        f14.parse_response(raw, ZTF, need_sep=True)


# ------------------------------------------------------------------------ url

def test_url_gives_negative_declination_an_explicit_sign():
    url = f14.build_url("https://h", "J/ApJS/249/18/table2", 215.54202, -84.44295, 21)
    assert "215.542020-84.442950" in url and "%2B-" not in url and "+-" not in url


def test_url_encodes_positive_declination_plus_sign():
    url = f14.build_url("https://h", "II/264/asas3", 10.0, 30.0, 30)
    assert "10.000000%2B30.000000" in url and "-c.u=arcsec" in url


# ------------------------------------------------------------------- retries

def test_query_retries_then_succeeds():
    calls = []

    def flaky(url, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("reset")
        return votable(ZTF, [])

    assert f14.query_catalog(ZTF, 10.0, 20.0, fetch=flaky, delay=0) == []
    assert len(calls) == 3


def test_query_that_always_fails_raises_instead_of_returning_empty():
    def down(url, timeout):
        raise OSError("down")

    with pytest.raises(OSError):
        f14.query_catalog(ZTF, 10.0, 20.0, fetch=down, delay=0)


def test_error_document_is_retried_and_then_raised():
    with pytest.raises(f14.CatalogError):
        f14.query_catalog(ZTF, 10.0, 20.0, fetch=lambda u, t: ERROR_DOC, delay=0)


# ------------------------------------------------------------- period matching

@pytest.mark.parametrize("cat_p,ours,ratio", [(3.0, 3.0, 1.0), (1.5, 3.0, 0.5), (6.0, 3.0, 2.0),
                                              (3.02, 3.0, 1.0)])
def test_period_match_ratios(cat_p, ours, ratio):
    m = f14.period_match([cat_p], [ours])
    assert m is not None and m[0] == ratio


def test_period_match_rejects_beyond_tolerance_and_other_ratios():
    assert f14.period_match([3.04], [3.0]) is None          # 1.3 percent off
    assert f14.period_match([1.0], [3.0]) is None           # ratio 1/3 not accepted
    assert f14.period_match([], [3.0]) is None


def test_period_match_tries_both_of_our_periods():
    assert f14.period_match([5.0], [2.5, 5.0]) is not None


# ------------------------------------------------------------------- evaluate

def _row(sep, per, cls="EW", tic=None, id_="S"):
    return {"sep_arcsec": sep, "periods": per, "cls": cls, "source_id": id_, "tic": tic,
            "ra": 1.0, "dec": 1.0}


def test_same_star_with_matching_period():
    o = f14.evaluate(ZTF, [_row(1.2, [1.5])], 100.0, 10.0, [3.0])
    assert o["status"] == "SAME_STAR_PERIOD_MATCH" and o["match_ratio"] == 0.5


def test_same_star_with_different_period():
    assert f14.evaluate(ZTF, [_row(1.2, [7.7])], 100.0, 10.0, [3.0])["status"] == "SAME_STAR_OTHER_PERIOD"


def test_same_star_without_any_period():
    assert f14.evaluate(ZTF, [_row(1.2, [])], 100.0, 10.0, [3.0])["status"] == "SAME_STAR_NO_PERIOD"


def test_nearby_source_is_not_called_same_star():
    assert f14.evaluate(ZTF, [_row(12.0, [3.0])], 100.0, 10.0, [3.0])["status"] == "NEARBY_PERIOD_MATCH"
    assert f14.evaluate(ZTF, [_row(12.0, [9.9])], 100.0, 10.0, [3.0])["status"] == "NEARBY_OTHER"


def test_matching_neighbour_does_not_override_a_same_star_source():
    rows = [_row(2.0, [9.9]), _row(14.0, [3.0])]
    assert f14.evaluate(ZTF, rows, 100.0, 10.0, [3.0])["status"] == "SAME_STAR_OTHER_PERIOD"


def test_asas_uses_its_wider_same_star_radius():
    assert f14.evaluate(ASAS, [_row(12.0, [3.0])], 100.0, 10.0, [3.0])["status"] == "SAME_STAR_PERIOD_MATCH"


def test_kelt_tic_equality_matches_at_any_separation():
    o = f14.evaluate(KELT, [_row(19.0, [3.0], tic=123)], 100.0, 10.0, [3.0], our_tic=123)
    assert o["status"] == "SAME_STAR_PERIOD_MATCH"
    o = f14.evaluate(KELT, [_row(19.0, [3.0], tic=999)], 100.0, 10.0, [3.0], our_tic=123)
    assert o["status"] == "NEARBY_PERIOD_MATCH"


def test_outside_footprint_is_not_a_clear_result():
    o = f14.evaluate(ZTF, [], 215.0, -84.0, [3.0])
    assert o["status"] == "NOT_COVERED" and o["covered"] is False


def test_empty_inside_footprint_is_no_match_and_kelt_coverage_is_unknown():
    assert f14.evaluate(ZTF, [], 100.0, 10.0, [3.0])["covered"] is True
    assert f14.evaluate(KELT, [], 100.0, 10.0, [3.0])["covered"] is None


# -------------------------------------------------------------------- verdicts

def _o(cat, status, covered=True):
    return {"catalog": cat, "status": status, "covered": covered}


def test_positive_beats_failure():
    assert f14.star_verdict([_o("ztf", "SAME_STAR_PERIOD_MATCH"), _o("crts", "QUERY_FAILED")]) == "ALREADY_KNOWN"


def test_failure_blocks_no_match():
    assert f14.star_verdict([_o("ztf", "NO_MATCH"), _o("crts", "QUERY_FAILED")]) == "INCOMPLETE"


def test_all_clear_is_no_match():
    assert f14.star_verdict([_o("ztf", "NO_MATCH"), _o("wise", "NO_MATCH")]) == "NO_MATCH"


def test_only_unknown_coverage_clear_is_weak():
    assert f14.star_verdict([_o("kelt", "NO_MATCH", None), _o("ztf", "NOT_COVERED", False)]) == "NO_MATCH_WEAK"


def test_nothing_covers_the_star():
    assert f14.star_verdict([_o("ztf", "NOT_COVERED", False)]) == "NOT_COVERED"


def test_verdict_precedence():
    assert f14.star_verdict([_o("ztf", "SAME_STAR_OTHER_PERIOD"), _o("crts", "NEARBY_PERIOD_MATCH")]) \
        == "KNOWN_VARIABLE_PERIOD_DIFFERS"
    assert f14.star_verdict([_o("ztf", "NEARBY_OTHER"), _o("crts", "NO_MATCH")]) == "NEARBY_VARIABLE"
    assert f14.star_verdict([_o("ztf", "NEARBY_PERIOD_MATCH"), _o("crts", "NEARBY_OTHER")]) \
        == "NEARBY_PERIOD_MATCH"


# ------------------------------------------------------- driver (no network)

def make_root(tmp_path, n=8):
    base = tmp_path / "site" / "public" / "data"
    (base / "detail").mkdir(parents=True)
    cands = []
    for i in range(n):
        tic = 1000 + i
        cands.append({"tic": tic, "tier": "CLEAN"})
        (base / "detail" / f"TIC{tic}.json").write_text(json.dumps(
            {"period_true_days": 3.0, "period_bls_days": 3.0,
             "catalog": {"ra": 100.0 + i, "dec": 10.0 + i}}), encoding="utf-8")
    (base / "index.json").write_text(json.dumps({"candidates": cands}), encoding="utf-8")
    (tmp_path / "data" / "processed").mkdir(parents=True)
    return str(tmp_path)


def test_candidates_load_with_both_periods(tmp_path):
    stars = f14.load_candidates(make_root(tmp_path, 3))
    assert [s["tic"] for s in stars] == [1000, 1001, 1002] and stars[0]["periods"] == [3.0]


def test_breaker_stops_a_dead_catalog_and_caches_only_successes(tmp_path, monkeypatch):
    stars = f14.load_candidates(make_root(tmp_path, 8))
    calls = []

    def dead(cat, ra, dec, host=None, **kw):
        calls.append(1)
        raise OSError("down")

    monkeypatch.setattr(f14, "query_catalog", dead)
    results = {}
    cache = str(tmp_path / "c.json")
    f14.run_catalog(ZTF, stars, cache, "h", False, results, lambda m: None)
    assert ("ztf", "TRIPPED") in results and len(calls) == f14.BREAKER_LIMIT
    assert json.load(open(cache)) == {}


def test_resume_uses_cache_and_skips_queries(tmp_path, monkeypatch):
    stars = f14.load_candidates(make_root(tmp_path, 4))
    cache = str(tmp_path / "c.json")
    monkeypatch.setattr(f14, "query_catalog", lambda *a, **k: [])
    f14.run_catalog(ZTF, stars, cache, "h", False, {}, lambda m: None)

    def must_not_run(*a, **k):
        raise AssertionError("cache should have been used")

    monkeypatch.setattr(f14, "query_catalog", must_not_run)
    results = {}
    f14.run_catalog(ZTF, stars, cache, "h", False, results, lambda m: None)
    assert all(results[("ztf", s["tic"])] == ([], None) for s in stars)


def test_cache_is_not_reused_if_coordinates_change(tmp_path, monkeypatch):
    stars = f14.load_candidates(make_root(tmp_path, 2))
    cache = str(tmp_path / "c.json")
    monkeypatch.setattr(f14, "query_catalog", lambda *a, **k: [])
    f14.run_catalog(ZTF, stars, cache, "h", False, {}, lambda m: None)
    moved = [dict(s, ra=s["ra"] + 1.0) for s in stars]
    n = []
    monkeypatch.setattr(f14, "query_catalog", lambda *a, **k: n.append(1) or [])
    f14.run_catalog(ZTF, moved, cache, "h", False, {}, lambda m: None)
    assert len(n) == 2


def test_failed_query_is_recorded_as_failed_never_as_no_match(tmp_path):
    stars = f14.load_candidates(make_root(tmp_path, 1))
    results = {(c["key"], stars[0]["tic"]): ([], None) for c in f14.CATALOGS}
    results[("crts", stars[0]["tic"])] = (None, "timeout")
    per_cat, per_star = f14.build_tables(stars, results)
    assert per_cat[per_cat.catalog == "crts"].iloc[0]["status"] == "QUERY_FAILED"
    assert per_star.iloc[0]["verdict"] == "INCOMPLETE" and per_star.iloc[0]["failed_catalogs"] == "crts"


def test_main_exits_3_and_writes_nothing_when_a_catalog_is_down(tmp_path, monkeypatch):
    root = make_root(tmp_path, 8)
    monkeypatch.setattr(f14, "self_test", lambda host: (True, []))

    def dead_zt(cat, ra, dec, host=None, **kw):
        if cat["key"] == "ztf":
            raise OSError("down")
        return []

    monkeypatch.setattr(f14, "query_catalog", dead_zt)
    assert f14.main([root]) == f14.EXIT_UPSTREAM_DOWN
    assert not os.path.exists(os.path.join(root, "data", "processed", "f14_novelty_extra.csv"))


def test_main_exits_3_when_service_unreachable(tmp_path, monkeypatch):
    root = make_root(tmp_path, 2)

    def unreachable(host):
        raise OSError("no route")

    monkeypatch.setattr(f14, "self_test", unreachable)
    assert f14.main([root]) == f14.EXIT_UPSTREAM_DOWN


def test_main_exits_1_on_schema_drift(tmp_path, monkeypatch):
    root = make_root(tmp_path, 2)
    monkeypatch.setattr(f14, "self_test", lambda host: (False, ["ztf: columns missing"]))
    assert f14.main([root]) == 1


def test_main_happy_path_writes_both_tables(tmp_path, monkeypatch):
    root = make_root(tmp_path, 3)
    monkeypatch.setattr(f14, "self_test", lambda host: (True, []))

    def fake(cat, ra, dec, host=None, **kw):
        if cat["key"] == "crts" and abs(ra - 101.0) < 1e-9:     # TIC 1001 is a known 3.0 d EB
            return [_row(0.8, [3.0])]
        return []

    monkeypatch.setattr(f14, "query_catalog", fake)
    assert f14.main([root]) == 0
    import pandas as pd
    s = pd.read_csv(os.path.join(root, "data", "processed", "f14_novelty_extra.csv"))
    assert dict(zip(s.tic, s.verdict))[1001] == "ALREADY_KNOWN"
    assert s[s.tic == 1000].iloc[0]["verdict"] == "NO_MATCH"
    c = pd.read_csv(os.path.join(root, "data", "processed", "f14_extra_catalogs.csv"))
    assert len(c) == 3 * len(f14.CATALOGS)
