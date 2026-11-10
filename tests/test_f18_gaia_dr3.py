import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f18_gaia_dr3 as g  # noqa: E402


def _sources(rows):
    cols = ["source_id", "ra", "dec", "phot_g_mean_mag", "bp_rp", "parallax", "parallax_error", "pmra", "pmdec", "ruwe",
            "astrometric_excess_noise", "phot_variable_flag", "non_single_star", "radial_velocity", "radial_velocity_error",
            "rv_nb_transits", "rv_chisq_pvalue", "rv_renormalised_gof"]
    base = dict(bp_rp=1.0, parallax=1.0, parallax_error=0.05, pmra=0.0, pmdec=0.0, ruwe=1.0, astrometric_excess_noise=0.0,
                phot_variable_flag="NOT_AVAILABLE", non_single_star=0, radial_velocity=np.nan, radial_velocity_error=np.nan,
                rv_nb_transits=np.nan, rv_chisq_pvalue=np.nan, rv_renormalised_gof=np.nan)
    return pd.DataFrame([dict(base, **r) for r in rows], columns=cols)


def test_pick_target_prefers_matching_brightness_over_a_closer_faint_star():
    s = _sources([
        {"source_id": 1, "ra": 10.0 + 0.5 / 3600, "dec": 20.0, "phot_g_mean_mag": 18.0},     # 0.5 arcsec away but 5.7 mag too faint
        {"source_id": 2, "ra": 10.0 + 2.0 / 3600, "dec": 20.0, "phot_g_mean_mag": 12.5},     # right brightness (Tmag 12.2)
    ])
    row, q = g.pick_target(s, 10.0, 20.0, 12.2)
    assert int(row["source_id"]) == 2 and q == "MATCHED"


def test_pick_target_flags_ambiguity_and_none():
    two = _sources([{"source_id": 1, "ra": 10.0 + 1.0 / 3600, "dec": 20.0, "phot_g_mean_mag": 12.5},
                    {"source_id": 2, "ra": 10.0 - 1.2 / 3600, "dec": 20.0, "phot_g_mean_mag": 12.6}])
    assert g.pick_target(two, 10.0, 20.0, 12.2)[1] == "AMBIGUOUS"
    far = _sources([{"source_id": 3, "ra": 10.0 + 20 / 3600, "dec": 20.0, "phot_g_mean_mag": 12.5}])
    assert g.pick_target(far, 10.0, 20.0, 12.2) == (None, "NONE")
    assert g.pick_target(_sources([]), 10.0, 20.0, 12.2) == (None, "NONE")
    wrong = _sources([{"source_id": 4, "ra": 10.0, "dec": 20.0, "phot_g_mean_mag": 17.0}])
    assert g.pick_target(wrong, 10.0, 20.0, 12.2)[1] == "AMBIGUOUS"          # 4.5 mag fainter than expected


def test_neighbours_exclude_the_target_and_use_gaia_ids():
    s = _sources([{"source_id": 1, "ra": 10.0, "dec": 20.0, "phot_g_mean_mag": 12.0},
                  {"source_id": 2, "ra": 10.0, "dec": 20.0 + 5 / 3600, "phot_g_mean_mag": 13.0},
                  {"source_id": 3, "ra": 10.0 + 80 / 3600, "dec": 20.0, "phot_g_mean_mag": 11.0}])    # beyond 63 arcsec
    n = g.gaia_neighbours(s, s.iloc[0])
    assert list(n["nbr_TIC"]) == [2] and n["sep_arcsec"].iloc[0] == pytest.approx(5.0, abs=0.01)


def test_contamination_uses_the_f15_rules_with_gaia_neighbours():
    # a neighbour 1 mag fainter, 3 arcsec away, where the centroid says the dimming is: unseparable
    near = pd.DataFrame({"nbr_TIC": [7], "nbr_Tmag": [13.0], "sep_arcsec": [3.0]})
    assert g.assess_contamination(0.02, 12.0, 3.0, 100.0, near)["status"] == "UNSEPARABLE_NEIGHBOUR"
    far_faint = pd.DataFrame({"nbr_TIC": [8], "nbr_Tmag": [20.0], "sep_arcsec": [30.0]})
    r = g.assess_contamination(0.02, 12.0, 3.0, 100.0, far_faint)
    assert r["status"] == "NO_VIABLE_NEIGHBOUR" and r["n_neighbours"] == 1


def test_rv_summary_says_when_nothing_is_known():
    assert g.rv_variability({"radial_velocity": np.nan})["has_rv"] is False
    faint = g.rv_variability({"radial_velocity": 12.0, "rv_chisq_pvalue": np.nan, "rv_nb_transits": 8})
    assert faint["has_rv"] and faint["variable"] is None
    assert g.rv_variability({"radial_velocity": 12.0, "rv_chisq_pvalue": 1e-6, "rv_nb_transits": 20})["variable"] is True
    assert g.rv_variability({"radial_velocity": 12.0, "rv_chisq_pvalue": 0.4, "rv_nb_transits": 20})["variable"] is False


def test_period_relation():
    assert g.period_relation(2.0, 2.01) == "same" and g.period_relation(2.0, 1.0) == "half"
    assert g.period_relation(2.0, 4.0) == "double" and g.period_relation(2.0, 3.3) == "unrelated"
    assert g.period_relation(None, 3.0) is None


def test_summarise_counts():
    rep = {"stars": {
        "1": {"match": "MATCHED", "ruwe_elevated": True, "contamination": {"status": "NO_VIABLE_NEIGHBOUR"}, "gaia_eb": {"relation": "same"}, "gaia_nss": None,
              "rv": {"has_rv": True, "variable": True}, "gaia_variability": "ECL"},
        "2": {"match": "NONE"},
        "3": {"match": "AMBIGUOUS", "ruwe_elevated": False, "contamination": {"status": "UNSEPARABLE_NEIGHBOUR"}, "gaia_eb": None, "gaia_nss": {"solution_type": "X"},
              "rv": {"has_rv": False, "variable": None}}}}
    s = g.summarise(rep)
    assert s["stars"] == 3 and s["matched"] == 1 and s["ambiguous"] == 1 and s["none"] == 1
    assert s["ruwe_elevated"] == 1 and s["in_gaia_eb_table"] == 1 and s["in_gaia_nss_orbit"] == 1 and s["rv_variable"] == 1
    assert s["contamination_status_gaia"] == {"NO_VIABLE_NEIGHBOUR": 1, "UNSEPARABLE_NEIGHBOUR": 1}
