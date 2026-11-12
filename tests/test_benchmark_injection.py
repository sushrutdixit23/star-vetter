import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import f29_benchmark as fb  # noqa: E402
import f30_injection as fi  # noqa: E402


def test_preregistration_is_complete_and_unchanged_in_shape():
    pre = json.loads((ROOT / "data" / "benchmarks" / "f29_preregistration.json").read_text(encoding="utf-8"))
    rule = pre["pass_rule"]
    assert (rule["e_abs"], rule["abs_esinw_abs"], rule["r_frac"], rule["incl_deg"]) == (0.01, 0.02, 0.05, 0.5)
    names = [s["name"] for s in pre["systems"]]
    assert names == ["MU Cas", "V1022 Cas", "V454 Aur", "V505 Per"]
    for s in pre["systems"]:
        tr = s["truth"]
        assert abs(np.hypot(tr["ecosw"], tr["esinw"]) - tr["e"]) < 0.002
        assert tr["r1"] + tr["r2"] < 0.25


def test_primary_duration_is_measured_from_a_box_eclipse():
    period, t0, dur = 5.0, 1000.0, 0.3
    t = np.arange(1000.0, 1060.0, 2.0 / 1440)
    ph = ((t - t0) / period + 0.5) % 1.0 - 0.5
    f = np.where(np.abs(ph) * period < dur / 2, 0.8, 1.0) + np.random.default_rng(1).normal(0, 1e-4, len(t))
    depth, d = fb.measure_primary(t, f, period, t0)
    assert abs(depth - 0.2) < 0.01
    assert 0.3 <= d <= 0.4          # the measured width is padded by 15%


def test_judge_applies_the_registered_rule():
    q = lambda m: {"median": m, "lo": 0.01, "hi": 0.01, "p2.5": m - 0.02, "p97.5": m + 0.02}  # noqa: E731
    row = {"status": "OK", "truth": {"e": 0.2, "esinw": -0.1, "ecosw": 0.17, "r1": 0.1, "r2": 0.08, "incl": 87.0},
           "fit": {"e": q(0.205), "esinw": q(0.105), "ecosw": q(0.171), "r1": q(0.103), "r2": q(0.081), "incl": q(87.3)}}
    out = fb.judge(dict(row), {"e_abs": 0.01, "abs_esinw_abs": 0.02, "ecosw_abs": 0.005, "r_frac": 0.05, "incl_deg": 0.5})
    assert out["passed"] is True          # |e sin w| compared, so the sign convention does not matter
    row["fit"]["r1"] = q(0.11)
    out = fb.judge(dict(row), {"e_abs": 0.01, "abs_esinw_abs": 0.02, "ecosw_abs": 0.005, "r_frac": 0.05, "incl_deg": 0.5})
    assert out["passed"] is False and out["checks"]["r1"] is False


def test_injected_systems_are_detached_and_eclipse_twice():
    rng = np.random.default_rng(29)
    for _ in range(200):
        p = fi.draw(rng)
        e = p["fc"] ** 2 + p["fs"] ** 2
        w = np.arctan2(p["fs"], p["fc"])
        assert 1 - e >= 1.5 * p["rsum"]
        for sign in (1, -1):
            rho = (1 - e * e) / (1 + sign * e * np.sin(w))
            assert rho * p["cosi"] < 0.7 * p["rsum"] + 1e-12


def test_coverage_metrics():
    def row(truth, med, sig, trusted):
        q = {"median": med, "lo": sig, "hi": sig, "p2.5": med - 2 * sig, "p97.5": med + 2 * sig}
        fit = {k: dict(q) for k in fi.QUANTITIES}
        fit["rsum"] = {"median": 0.1}
        return {"status": "OK", "host": 1, "index": 0, "trusted": trusted, "fit": fit,
                "truth": {k: truth for k in fi.QUANTITIES}, "inputs": {"f22": {"verdict": "ECCENTRIC"}}}
    rows = [row(0.2, 0.2 + d, 0.01, True) for d in (0.0, 0.005, -0.005, 0.02)]
    m = fi.metrics(rows)
    assert m["by_quantity"]["e"]["coverage_68"] == 0.75
    assert m["trust_rule"]["accepted"] == 4 and m["trust_rule"]["accepted_good_fraction"] == 1.0
