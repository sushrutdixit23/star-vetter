import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f20_evidence as ev  # noqa: E402


def _row(**kw):
    base = {"tier": "CLEAN", "p_tess": 3.0, "ztf": None, "gaia": None, "neigh": {"status": "NO_VIABLE_NEIGHBOUR"}, "prior": None,
            "novelty": {"verdict": "NO_MATCH"}, "toi": None}
    base.update(kw)
    return base


def _gaia(period=None, sol="SB1", status="NO_VIABLE_NEIGHBOUR", ruwe=False, match="MATCHED"):
    return {"match": match, "ruwe_elevated": ruwe, "contamination": {"status": status},
            "gaia_nss": None if period is None else {"solution_type": sol, "period_days": period}}


def test_ztf_confirmation_is_an_independent_line():
    r = ev.assess_star(_row(ztf={"status": "CONFIRMED", "p_value": 0.003, "power": 0.9}, gaia=_gaia()))
    assert r["evidence_tier"] == "INDEPENDENTLY_SUPPORTED" and len(r["independent_lines"]) == 1


def test_gaia_sb1_at_the_tess_period_or_its_double_is_an_independent_line():
    assert ev.assess_star(_row(gaia=_gaia(period=3.002)))["evidence_tier"] == "INDEPENDENTLY_SUPPORTED"
    assert ev.assess_star(_row(gaia=_gaia(period=6.0)))["gaia_period_relation"] == "double"
    # a 450-day astrometric orbit says nothing about a 3-day eclipsing pair
    r = ev.assess_star(_row(gaia=_gaia(period=450.0, sol="Orbital")))
    assert r["evidence_tier"] == "TESS_ONLY_CLEAN" and r["gaia_period_relation"] is None


def test_not_seen_by_a_capable_ztf_is_evidence_against_and_wins_over_support():
    r = ev.assess_star(_row(ztf={"status": "NOT_SEEN", "power": 0.95}, gaia=_gaia(period=3.0)))
    assert r["evidence_tier"] == "DISFAVOURED" and r["against"]
    assert ev.assess_star(_row(ztf={"status": "INCONCLUSIVE", "power": 0.1}))["evidence_tier"] == "TESS_ONLY_CLEAN"   # not testable: no verdict either way
    assert ev.assess_star(_row(prior={"toi": {"toi": "1.01", "disposition": "PC"}}))["evidence_tier"] == "DISFAVOURED"


def test_caveats_demote_tess_only_stars():
    for kw in ({"tier": "PERIOD ALIAS"}, {"neigh": {"status": "UNSEPARABLE_NEIGHBOUR"}}, {"gaia": _gaia(ruwe=True)},
               {"gaia": _gaia(status="VIABLE_NEIGHBOUR_AT_OFFSET")}, {"gaia": _gaia(match="AMBIGUOUS")}):
        assert ev.assess_star(_row(**kw))["evidence_tier"] == "TESS_ONLY_CAVEATS", kw


def test_odd_even_difference_in_ztf_is_a_caveat_on_a_confirmed_star():
    z = {"status": "CONFIRMED", "p_value": 0.003, "power": 0.9, "odd_even_at_2P": {"z": 4.5}}
    r = ev.assess_star(_row(ztf=z))
    assert r["evidence_tier"] == "INDEPENDENTLY_SUPPORTED" and any("twice" in c for c in r["caveats"])


def test_novelty_labels():
    simb = lambda main, ot, grp="other": {"simbad": {"main_id": main, "otype": ot, "group": grp}}   # noqa: E731
    assert ev.novelty_label({"verdict": "ALREADY_KNOWN"}, None, None, 3.0)[0] == "KNOWN_ECLIPSING"
    assert ev.novelty_label(None, simb("NGTS-EB-8", "SB*"), None, 3.0)[0] == "KNOWN_ECLIPSING"          # name says eclipsing binary
    assert ev.novelty_label(None, simb("V* X", "EB*", "eclipsing_binary"), None, 3.0)[0] == "KNOWN_ECLIPSING"
    assert ev.novelty_label(None, {"in_new_catalogs": [{"id": "J/AJ/171/29", "source": "x"}]}, None, 3.0)[0] == "KNOWN_ECLIPSING"
    assert ev.novelty_label(None, None, _gaia(period=3.0), 3.0)[0] == "KNOWN_BINARY"
    assert ev.novelty_label(None, simb("HD 1", "**"), None, 3.0)[0] == "KNOWN_BINARY"
    assert ev.novelty_label({"verdict": "KNOWN_VARIABLE_PERIOD_DIFFERS"}, None, None, 3.0)[0] == "KNOWN_VARIABLE"
    assert ev.novelty_label({"verdict": "NO_MATCH"}, simb("TYC 1", "*", "plain_star"), None, 3.0) == ("NO_PRIOR_FOUND", [])
    assert not ev.EB_NAME.search("REBEL 5") and ev.EB_NAME.search("NGTS-EB-8")


def test_summary_counts():
    stars = {"1": {"evidence_tier": "INDEPENDENTLY_SUPPORTED", "novelty": "KNOWN_BINARY", "ztf_status": "CONFIRMED"},
             "2": {"evidence_tier": "TESS_ONLY_CLEAN", "novelty": "NO_PRIOR_FOUND", "ztf_status": "NO_DATA"}}
    s = ev.summarise(stars)
    assert s["stars"] == 2 and s["by_evidence_tier"]["INDEPENDENTLY_SUPPORTED"] == 1 and s["tier_by_novelty"]["TESS_ONLY_CLEAN|NO_PRIOR_FOUND"] == 1
