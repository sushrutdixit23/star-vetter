import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import predict_period_change as ppc  # noqa: E402
import export_findings as ef  # noqa: E402


def make_groups(c2=0.003, n=30, seed=1):
    rng = np.random.default_rng(seed)
    E = np.linspace(-20, 140, n)
    return [{"source": "TESS" if e > 40 else "ZTF", "epoch": float(e), "oc_min": float(c2 * e * e - 0.5 * e + rng.normal(0, 2.0)), "err_min": 2.0}
            for e in E]


def test_parabola_predictions_follow_the_true_curve_within_their_errors():
    P, t0 = 10.0, 2459000.0
    out = ppc.predict(make_groups(), P, t0, t0 + 150 * P, t0 + 175 * P)
    pr = out["predictions"]
    assert len(pr) == 26
    for r in pr:
        e = r["epoch"]
        truth = t0 + e * P + (0.003 * e * e - 0.5 * e) / 1440.0
        assert abs(r["bjd_tdb_parabola"] - truth) * 1440.0 < 4 * r["sigma_min"]
    assert pr[-1]["sigma_min"] > pr[0]["sigma_min"]          # uncertainty grows with distance


def test_predictions_are_deterministic():
    P, t0 = 10.0, 2459000.0
    a = ppc.predict(make_groups(), P, t0, t0 + 1500, t0 + 1600)
    b = ppc.predict(make_groups(), P, t0, t0 + 1500, t0 + 1600)
    assert a == b


def test_findings_markdown_has_no_non_ascii_and_states_the_limits():
    o = {"verdict_counts": {"ECCENTRIC": 1}, "candidates": [{
        "tic": 1, "period_days": 5.0, "ecosw": 0.2, "ecosw_sigma": 0.001, "secondary_snr": 20, "ztf_confirmed": None,
        "ztf_coverage": "no_file", "ztf_p_value": None, "evidence_tier": "TESS_ONLY_CLEAN", "novelty": "NO_PRIOR_FOUND", "marginal": False}],
        "circularisation": {"threshold_ecosw": 0.05, "n_short": 10, "k_short": 0, "n_longer": 20, "k_longer": 4,
                            "chance_of_none_if_same_rate_as_longer": 0.1},
        "period_bins": [{"p_min": 0.0, "p_max": 2.0, "n_measured": 10, "n_offset": 0}],
        "timing_drift": None, "limits": ["lower limit"]}
    md = ef.markdown(o)
    assert md.isascii()
    assert "lower limit" in md
