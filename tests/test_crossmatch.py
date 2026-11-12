"""
Tests for crossmatch.py (the VizieR stand-in for CDS XMatch) and the 2026-11-12 pre-flight changes in upstream.py.

No network: the VizieR request is replaced by a stub that returns astropy Tables shaped like the real answer
(a `_q` column holding the 1-based index of the input position, plus the catalog's own columns).
"""
import sys
import warnings
from pathlib import Path

import astropy.units as u
import numpy as np
import pandas as pd
import pytest
from astropy.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import crossmatch as cx  # noqa: E402
import upstream  # noqa: E402


def stars(n=10):
    return pd.DataFrame({"TIC": 5000 + np.arange(n), "ra": 10.0 + np.arange(n) * 0.01, "dec": 20.0 + np.zeros(n)})


def vsx_answer(coords, rows):
    """rows: list of (input index, d_ra_arcsec, name); builds the table VizieR would send."""
    ra = [coords[i].ra.deg + d / 3600.0 for i, d, _ in rows]
    return Table({"_q": [i + 1 for i, _, _ in rows], "RAJ2000": ra, "DEJ2000": [coords[i].dec.deg for i, _, _ in rows],
                  "Name": [n for _, _, n in rows], "Type": ["EB"] * len(rows)})


def test_nearest_match_per_star_and_radius_cut():
    df = stars(10)

    def query(coords, radius, src):
        # star 2 has two catalog neighbours (3.0 and 1.0 arcsec), star 4 one at 9 arcsec (outside 5), star 7 one at 2
        return vsx_answer(coords, [(2, 3.0, "far"), (2, 1.0, "near"), (4, 9.0, "outside"), (7, 2.0, "ok")])

    out = cx.crossmatch(df, "B/vsx/vsx", 5.0, query=query, log=lambda *_: None)
    got = out.set_index("TIC")
    assert sorted(got.index) == [5002, 5007]                 # 5004 is outside the 5 arcsec radius
    assert got.loc[5002, "Name"] == "near"                   # nearest wins
    # the stub offsets RA by 1 arcsec of coordinate, which is cos(dec) arcsec on the sky
    assert got.loc[5002, "angDist"] == pytest.approx(np.cos(np.radians(20.0)), abs=0.01)


def test_chunks_map_back_to_the_right_stars():
    df = stars(10)
    seen = []

    def query(coords, radius, src):
        seen.append(len(coords))
        return vsx_answer(coords, [(0, 1.0, "first of chunk")])   # the first star of EVERY chunk matches

    out = cx.crossmatch(df, "B/vsx/vsx", 5.0, chunk=4, query=query, log=lambda *_: None)
    assert seen == [4, 4, 2]
    assert sorted(out["TIC"]) == [5000, 5004, 5008]


def test_no_matches_is_an_empty_table_not_an_error():
    out = cx.crossmatch(stars(5), "B/vsx/vsx", 5.0, query=lambda c, r, s: None, log=lambda *_: None)
    assert len(out) == 0 and "TIC" in out.columns


def test_failed_request_is_retried_then_split_then_recovers(monkeypatch):
    monkeypatch.setattr(cx.time, "sleep", lambda *_: None)
    df = stars(60)
    calls = []

    def query(coords, radius, src):
        calls.append(len(coords))
        if len(coords) > 30:                                  # the server chokes on big requests
            raise RuntimeError("truncated VOTable")
        return vsx_answer(coords, [(0, 1.0, "m")])

    out = cx.crossmatch(df, "B/vsx/vsx", 5.0, chunk=60, min_split=25, retries=1, query=query, log=lambda *_: None)
    assert calls[:2] == [60, 60]                              # 1 try + 1 retry at full size
    assert calls[2:] == [30, 30]                              # then two halves, each fine
    assert sorted(out["TIC"]) == [5000, 5030]


def test_unrecoverable_failure_raises_instead_of_returning_a_partial_table(monkeypatch):
    monkeypatch.setattr(cx.time, "sleep", lambda *_: None)

    def query(coords, radius, src):
        raise RuntimeError("server error")

    with pytest.raises(upstream.UpstreamDown):
        cx.crossmatch(stars(40), "B/vsx/vsx", 5.0, chunk=40, min_split=25, retries=1, query=query, log=lambda *_: None)


def test_answer_without_coordinate_columns_is_refused():
    def query(coords, radius, src):
        return Table({"_q": [1], "Name": ["x"]})

    with pytest.raises(upstream.UpstreamDown):
        cx.crossmatch(stars(3), "B/vsx/vsx", 5.0, query=query, log=lambda *_: None)


def test_unknown_catalog_is_a_programming_error():
    with pytest.raises(ValueError):
        cx.crossmatch(stars(3), "J/not/known", 5.0, query=lambda c, r, s: None)


def test_truncated_votable_warning_becomes_a_failure(monkeypatch):
    """astroquery warns and returns an EMPTY result for a cut-off response. That must not read as 'no matches'."""
    class Truncating:
        def query_region(self, *a, **k):
            warnings.warn("VOTABLE parsing raised exception: 239:0: no element found")
            return []

    monkeypatch.setattr(cx, "vizier_for", lambda *a, **k: Truncating())
    query = cx._vizier_query("any.server")
    with pytest.raises(RuntimeError, match="truncated"):
        query(None, 5 * u.arcsec, "B/vsx/vsx")


def test_clean_empty_answer_is_not_a_failure(monkeypatch):
    class Quiet:
        def query_region(self, *a, **k):
            return []

    monkeypatch.setattr(cx, "vizier_for", lambda *a, **k: Quiet())
    assert cx._vizier_query("any.server")(None, 5 * u.arcsec, "B/vsx/vsx") is None


# ---------------------------------------------------------------- upstream.py (2026-11-12)

def status(**kw):
    return {k: (v, "test") for k, v in kw.items()}


def test_xmatch_down_is_not_a_blocker_when_a_vizier_server_works():
    s = status(mast=True, xmatch=False, vizier=False, vizier_mirror=True)
    assert upstream.problems(s, explicit=False) == []


def test_no_vizier_server_is_a_blocker():
    s = status(mast=True, xmatch=True, vizier=False, vizier_mirror=False)
    assert len(upstream.problems(s, explicit=False)) == 1


def test_mast_down_is_a_blocker():
    s = status(mast=False, xmatch=True, vizier=True, vizier_mirror=True)
    assert upstream.problems(s, explicit=False) == [upstream.SERVICES["mast"][0]]


def test_naming_services_on_the_command_line_still_requires_all_of_them():
    s = status(mast=True, xmatch=False)
    assert upstream.problems(s, explicit=True) == [upstream.SERVICES["xmatch"][0]]


def test_vizier_probe_is_a_real_query_that_must_return_2xx():
    for name in ("vizier", "vizier_mirror"):
        label, url, strict = upstream.SERVICES[name]
        assert strict is True and "/viz-bin/votable?" in url
    assert upstream.SERVICES["xmatch"][2] is False


def test_probe_strict_treats_404_as_down(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(upstream.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(upstream.time, "sleep", lambda *_: None)
    assert upstream.probe("http://x.invalid/", strict=False)[0] is True     # a front page answering 404 counted as up
    assert upstream.probe("http://x.invalid/", strict=True)[0] is False     # a query endpoint answering 404 does not


def test_pick_vizier_server_prefers_cds_then_mirror_then_none(monkeypatch):
    monkeypatch.delenv("STAR_VETTER_VIZIER_SERVER", raising=False)
    up = {upstream.SERVICES["vizier"][1]: True, upstream.SERVICES["vizier_mirror"][1]: True}
    pick = lambda: upstream.pick_vizier_server(lambda url, strict=False: (up[url], "", 0.0))  # noqa: E731
    assert pick() == upstream.CDS_SERVER
    up[upstream.SERVICES["vizier"][1]] = False
    assert pick() == upstream.MIRROR_SERVER
    up[upstream.SERVICES["vizier_mirror"][1]] = False
    assert pick() is None
    monkeypatch.setenv("STAR_VETTER_VIZIER_SERVER", "forced.example")
    assert pick() == "forced.example"


def test_vizier_requests_bypass_the_disk_cache(monkeypatch):
    """A retry must ask the server again, not replay a cached cut-off answer."""
    seen = {}

    class Spy:
        def query_region(self, *a, **k):
            seen.update(k)
            return []

    monkeypatch.setattr(cx, "vizier_for", lambda *a, **k: Spy())
    cx._vizier_query("any.server")(None, 5 * u.arcsec, "B/vsx/vsx")
    assert seen.get("cache") is False


# ---------------------------------------------------------------- errors reported inside a 200 response

class FakeResp:
    def __init__(self, text):
        self.text = text


GOOD = '<?xml version="1.0"?><VOTABLE><RESOURCE></RESOURCE></VOTABLE>\n'
ERR = ('<VOTABLE><INFO name="Error" value="Postgres connect error"/>'
       '<INFO name="QUERY_STATUS" value="ERROR"> -- no connection </INFO></VOTABLE>')


def test_error_inside_a_200_response_raises():
    """The mirror's 'Postgres connect error' answer used to be read as 'no catalog entry here'."""
    with pytest.raises(cx.VizierServerError, match="Postgres"):
        cx.check_vizier_response(FakeResp(ERR))


def test_cut_off_document_raises():
    with pytest.raises(cx.VizierServerError, match="cut off"):
        cx.check_vizier_response(FakeResp('<VOTABLE><RESOURCE><TABLE><DATA><TABLEDATA><TR><TD>1'))


def test_good_and_non_votable_responses_pass_through():
    r = FakeResp(GOOD)
    assert cx.check_vizier_response(r) is r
    page = FakeResp("<html>not a votable</html>")
    assert cx.check_vizier_response(page) is page


def test_harden_sets_server_and_installs_the_hook_once():
    class V:
        class S:
            hooks = {"response": []}
        _session = S()

    v = V()
    cx.harden(v, "x.example")
    cx.harden(v, "x.example")
    assert v.VIZIER_SERVER == "x.example"
    assert v._session.hooks["response"].count(cx.check_vizier_response) == 1


def test_harden_tolerates_objects_without_a_session():
    class Bare:
        pass

    b = cx.harden(Bare(), "y.example")
    assert b.VIZIER_SERVER == "y.example"
