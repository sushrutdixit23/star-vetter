import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft_rnaas as dr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "site" / "public" / "data"
NEEDED = ["audit.json", "recovery.json", "atlas_alias.json", "neighbours.json", "predictions.json",
          "novelty_extra.json", "tess_catalog_xmatch.json"]

pytestmark = pytest.mark.skipif(not all((D / n).exists() for n in NEEDED), reason="data files not generated")


def _data():
    return [json.loads((D / n).read_text(encoding="utf-8")) for n in NEEDED]


def _text():
    return dr.render(*_data())


def test_within_rnaas_limits():
    t = _text()
    assert dr.word_count(t) <= dr.WORD_LIMIT
    assert dr.table_count(t) == 1                      # one table, and no figure markup
    assert "![" not in t and "<img" not in t


def test_plain_ascii_and_no_hype():
    t = _text()
    assert t.isascii()
    for w in ("discover", "breakthrough", "groundbreaking", "revolution", "first-ever"):
        assert w not in t.lower(), w
    assert not re.search(r"\bnovel\b", t.lower())      # 'novelty' as a noun is fine


def test_numbers_come_from_the_data_files():
    audit, rec, alias, nb, pred, nov, xm = _data()
    t = _text()
    f = {x["key"]: x["count"] for x in audit["funnel"]}
    for n in (f["sampled"], f["usable"], f["on_target"], rec["counts"]["injections"], alias["tested"], pred["counts"]["listed"]):
        assert format(n, ",") in t or str(n) in t
    assert "%d of %d" % (alias["explained"]["k"], 0) not in t     # sanity: no stray format output
    assert "%s" not in t and "%d" not in t and "nan" not in t.lower().split()
    assert not re.search(r"[:(=] ?None\b", t)             # no unformatted Python values


def test_table_matches_predictions_exactly():
    audit, rec, alias, nb, pred, nov, xm = _data()
    t = _text()
    rows = [l for l in t.splitlines() if re.match(r"^\| \d{6,}", l)]
    assert len(rows) == len(pred["stars"])
    for s in pred["stars"]:
        line = next(l for l in rows if l.startswith("| %d |" % s["tic"]))
        assert "%.4f" % (s["ephemeris"]["t0_btjd"] + 2457000.0) in line
        assert "%.4f" % (s["predictions"][0]["t_btjd"] + 2457000.0) in line
        assert s["grade"].capitalize() in line
    assert "all %d predicted minima" % sum(len(s["predictions"]) for s in pred["stars"]) in t


def test_does_not_invent_a_doi_or_orcid_and_flags_the_ai_statement_for_confirmation():
    t = _text()
    assert "10.5281" not in t and "orcid.org" not in t
    fields = re.findall(r"\[\[.*?\]\]", t)
    assert len(fields) == 4
    assert any("Zenodo DOI" in x for x in fields) and any("confirm" in x.lower() for x in fields)
    assert "responsibility for the final manuscript text lies entirely with the author" in t


def test_states_that_the_stars_are_not_new_detections_and_gives_the_outcome_rule():
    t = _text()
    assert "not new detections" in t
    assert "within 3 sigma" in t and "whatever its outcome" in t


def test_word_count_ignores_table_separators():
    assert dr.word_count("a b\n|---|---|\n| c | d |") == 4
    assert dr.table_count("x\n|---|---|\ny") == 1


EXTRA = ["evidence.json", "ztf_independent.json", "gaia_dr3.json", "prior_art.json", "recovery_min2.json"]
needs_extra = pytest.mark.skipif(not all((D / n).exists() for n in EXTRA), reason="independent-evidence files not generated")


def _full_text():
    ev, ztf, g, pa, r2 = [json.loads((D / n).read_text(encoding="utf-8")) for n in EXTRA]
    return dr.render(*_data(), ev=ev, ztf=ztf, gdr3=g, prior=pa, rec2=r2)


@needs_extra
def test_full_note_stays_within_limits_and_is_ascii():
    t = _full_text()
    assert dr.word_count(t) <= dr.WORD_LIMIT
    assert dr.table_count(t) == 1
    assert t.isascii()
    assert "%s" not in t and "%d" not in t and not re.search(r"[:(=] ?None\b", t)


@needs_extra
def test_independent_numbers_come_from_the_files_and_the_catalog_caveat_is_stated():
    ev, ztf, g, pa, r2 = [json.loads((D / n).read_text(encoding="utf-8")) for n in EXTRA]
    t = _full_text()
    ct = ztf["summary"]["confirmed_among_testable"]
    assert "%d of the %d stars it could have tested" % (ct["k"], ct["n"]) in t
    assert "Absence from catalogs is largely by construction" in t
    assert "3-minute term" in t
    assert "lower bound" in t
    nv = ev["summary"]["by_novelty"]
    assert "%d are already known as eclipsing binaries" % nv.get("KNOWN_ECLIPSING", 0) in t
    assert "Gaia DR4" in t and "not excluded" in t       # what has not been done is said, not implied


def test_author_fields_and_doi_fill_the_note_without_inventing_anything():
    pre = {"doi": "10.5281/zenodo.1", "deposited_utc": "2026-11-10T17:06:14Z", "repo": "https://example.org/r",
           "bundle_sha256": "ab" * 32, "commit": "d85f405" + "0" * 33}
    fields = {"name": "A B", "affiliation": "Somewhere", "orcid": "0000-0000-0000-0000", "ai_usage_confirmed": False}
    t = dr.render(*_data(), prereg=pre, fields=fields)
    assert "doi:10.5281/zenodo.1, deposited 2026-11-10 UTC" in t
    assert "ORCID 0000-0000-0000-0000" in t
    left = re.findall(r"\[\[.*?\]\]", t)
    assert left == ["[[Author to confirm before submission.]]"]      # the AI statement is never confirmed for the author
    t2 = dr.render(*_data(), prereg=pre, fields=dict(fields, ai_usage_confirmed=True))
    assert not re.findall(r"\[\[.*?\]\]", t2)
