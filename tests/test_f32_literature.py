import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import f32_literature_check as lit  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON")
        return self._payload


class FakeSession:
    """Returns a canned answer per query type, or a failure for every query."""

    def __init__(self, fail=None, objects=(), refs=()):
        self.fail, self.objects, self.refs, self.calls = fail, list(objects), list(refs), 0

    def post(self, url, data=None, timeout=None):
        self.calls += 1
        if self.fail == "503":
            return FakeResponse(503)
        if self.fail == "error-document":
            return FakeResponse(200, {"error": "database not reachable"})
        q = data["query"]
        if "FROM ref" in q:
            return FakeResponse(200, {"metadata": [], "data": self.refs})
        if "JOIN ident" in q:
            return FakeResponse(200, {"metadata": [], "data": [o[:6] + ["TIC 1"] for o in self.objects]})
        return FakeResponse(200, {"metadata": [], "data": [o[:6] + [1.5] for o in self.objects]})


STAR = {"tic": 1, "gaia_id": "123", "ra": 10.0, "dec": 20.0, "tmag": 12.0, "period_days": 5.0, "e": 0.2, "omega_deg": 30.0}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(lit.time, "sleep", lambda s: None)


def test_reference_kinds_separate_surveys_from_studies():
    assert lit.classify_reference("Gaia Data Release 3 Stellar multiplicity", 307214) == ("survey", False)
    kind, binary = lit.classify_reference("Apsidal motion in the eclipsing binary XY Foo", 3)
    assert kind == "study" and binary is True
    assert lit.classify_reference("A catalog", 50)[0] == "mid"


def test_verdicts():
    study = {"kind": "study"}
    survey = {"kind": "survey"}
    assert lit.verdict_for([]) == "NOT_IN_SIMBAD"
    assert lit.verdict_for([{"references": []}]) == "IN_SIMBAD_NO_REFERENCES"
    assert lit.verdict_for([{"references": [survey, survey]}]) == "IN_SIMBAD_SURVEY_PAPERS_ONLY"
    assert lit.verdict_for([{"references": [survey]}, {"references": [study]}]) == "IN_SIMBAD_WITH_STUDIES"


@pytest.mark.parametrize("mode", ["503", "error-document"])
def test_a_failed_query_makes_the_star_unchecked_never_not_in_simbad(mode):
    rec = lit.check_star(STAR, session=FakeSession(fail=mode))
    assert rec["status"] == "UNCHECKED" and rec["verdict"] == "UNCHECKED"
    assert rec["objects"] == [] and rec["reason"]


def test_an_empty_but_complete_answer_is_not_in_simbad():
    rec = lit.check_star(STAR, session=FakeSession())
    assert rec["status"] == "CHECKED" and rec["verdict"] == "NOT_IN_SIMBAD"


def test_object_and_references_are_collected_and_sorted_newest_first():
    obj = [7, "V* Foo", "SB*", 3, 10.0, 20.0]
    refs = [["2001A", 2001, "J", "Old paper on the eclipsing binary Foo", 1, None], ["2023B", 2023, "J", "Survey", 300000, None]]
    rec = lit.check_star(STAR, session=FakeSession(objects=[obj], refs=refs))
    assert rec["verdict"] == "IN_SIMBAD_WITH_STUDIES"
    got = rec["objects"][0]["references"]
    assert [r["year"] for r in got] == [2023, 2001]
    assert got[0]["kind"] == "survey" and got[1]["kind"] == "study" and got[1]["mentions_binary_topics"]
    assert rec["objects"][0]["sep_arcsec"] == 1.5


def test_trusted_eccentric_stars_follow_the_trust_rule_in_the_committed_data():
    ecc = json.loads((ROOT / "site/public/data/eccentric.json").read_text(encoding="utf-8"))
    expected = sorted(r["tic"] for r in ecc["physical"]["fits"] if r.get("status") == "OK" and r.get("e_reliable") and r["e"]["median"] >= 0.02)
    got = [s["tic"] for s in lit.trusted_eccentric_stars(ROOT)]
    assert sorted(got) == expected and got
    # a star whose fit is circular (e = 0.000) or whose e is not trusted must not be in the list
    assert 237115819 not in got and 201317466 not in got and 43785616 not in got
    periods = [s["period_days"] for s in lit.trusted_eccentric_stars(ROOT)]
    assert periods == sorted(periods)


def test_the_committed_literature_file_covers_exactly_the_current_trusted_stars_and_is_complete():
    d = json.loads((ROOT / "data/processed/f32_literature.json").read_text(encoding="utf-8"))
    assert d["n_unchecked"] == 0
    assert "IN_SIMBAD_WITH_STUDIES" in d["control"]
    assert sorted(s["tic"] for s in d["stars"]) == sorted(s["tic"] for s in lit.trusted_eccentric_stars(ROOT)), \
        "the trusted-eccentric set changed: rerun py f32_literature_check.py ."


def test_markdown_is_ascii_names_unchecked_stars_and_lists_one_ads_query_per_star(tmp_path):
    rec_ok = lit.check_star(STAR, session=FakeSession())
    rec_bad = lit.check_star(dict(STAR, tic=2, gaia_id="456"), session=FakeSession(fail="503"))
    out = tmp_path / "lit.md"
    lit.write_markdown(out, [rec_ok, rec_bad], "2026-01-01T00:00:00Z", labels={1: ("NO_PRIOR_FOUND", "TESS_ONLY_CLEAN")})
    text = out.read_text(encoding="utf-8")
    assert all(ord(c) < 128 for c in text)
    assert "UNCHECKED" in text and "no object by TIC" in text
    assert 'full:"TIC 1" OR full:"123"' in text and 'full:"TIC 2" OR full:"456"' in text
    assert "NO_PRIOR_FOUND" in text


def test_the_control_detects_a_broken_lookup():
    # a session that finds nothing must fail the positive control, so "not in SIMBAD" is never trusted from a dead lookup
    ok, text = lit.run_control(session=FakeSession())
    assert ok is False and "NOT_IN_SIMBAD" in text
