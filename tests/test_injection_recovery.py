import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import injection_recovery as ir  # noqa: E402


def test_eclipse_model_depth_width_and_secondary():
    t = np.arange(0, 10, 0.001)
    m = ir.eclipse_model(t, period=2.0, t0=0.5, duration=0.2, ingress_frac=0.5, depth1=0.1, depth2=0.04)
    assert m.max() == pytest.approx(0.1, abs=1e-6)
    assert m.min() == 0.0
    # primary at 0.5 + 2k, secondary at 1.5 + 2k
    assert m[np.argmin(np.abs(t - 0.5))] == pytest.approx(0.1, abs=1e-6)
    assert m[np.argmin(np.abs(t - 1.5))] == pytest.approx(0.04, abs=1e-6)
    # zero outside the half duration
    assert m[np.argmin(np.abs(t - 0.5 - 0.11))] == 0.0
    # width at zero depth threshold is the stated duration
    first = t[(t > 0.3) & (t < 0.7) & (m > 1e-9)]
    assert first.max() - first.min() == pytest.approx(0.2, abs=0.005)


def test_v_shape_and_no_secondary():
    t = np.linspace(0, 4, 4001)
    m = ir.eclipse_model(t, 2.0, 0.0, 0.2, 1.0, 0.1, 0.0)
    near_secondary = m[np.abs(t - 1.0) < 0.2]
    assert near_secondary.max() == 0.0
    assert m.max() == pytest.approx(0.1, abs=1e-3)


def test_inject_is_multiplicative_and_places_t0_in_first_period():
    t = np.linspace(100, 110, 2000)
    flux = np.full_like(t, 2.0)
    p = {"period": 3.0, "depth1": 0.05, "depth2": 0.0, "duration": 0.3, "ingress_frac": 0.5, "t0_frac": 0.25}
    out, t0 = ir.inject(flux, t, p, 100.0)
    assert t0 == pytest.approx(100.75)
    assert out.max() == pytest.approx(2.0)
    assert out.min() == pytest.approx(2.0 * 0.95, rel=2e-3)


def test_draw_injection_is_reproducible_and_inside_the_prior():
    a = ir.draw_injection(np.random.default_rng(5), 27.0)
    b = ir.draw_injection(np.random.default_rng(5), 27.0)
    assert a == b
    for s in range(200):
        d = ir.draw_injection(np.random.default_rng(s), 27.0)
        assert ir.PRIOR["period_days"][0] <= d["period"] <= ir.PRIOR["period_days"][1]
        assert ir.PRIOR["primary_depth"][0] <= d["depth1"] <= ir.PRIOR["primary_depth"][1]
        assert 0 < d["duration"] < d["period"]
        assert d["depth2"] <= d["depth1"] + 1e-12
        assert d["searchable"] == (d["period"] <= 13.5)


def test_block_shuffle_keeps_values_and_breaks_periodicity():
    rng = np.random.default_rng(1)
    t = np.arange(0, 60, 0.02)
    flux = 1.0 + 0.001 * rng.normal(size=len(t)) - ir.eclipse_model(t, 3.0, 1.0, 0.2, 0.5, 0.05)
    sh = ir.block_shuffle(flux, t, np.random.default_rng(2))
    assert len(sh) == len(flux)
    assert np.allclose(np.sort(sh), np.sort(flux))
    assert not np.allclose(sh, flux)
    # eclipses are no longer on a 3-day comb
    fold_before = np.array([flux[(np.abs(((t - 1.0 + 1.5) % 3.0) - 1.5) < 0.05)].mean(), flux[(np.abs(((t - 2.5 + 1.5) % 3.0) - 1.5) < 0.05)].mean()])
    fold_after = sh[(np.abs(((t - 1.0 + 1.5) % 3.0) - 1.5) < 0.05)].mean()
    assert fold_before[0] < 0.98
    assert fold_after > fold_before[0] + 0.02     # the comb of dips is largely gone


@pytest.mark.parametrize("passed,bls,true,want", [
    (False, 3.0, 3.0, "missed"),
    (True, 3.01, 3.0, "exact"),
    (True, 1.5, 3.0, "alias"),
    (True, 6.0, 3.0, "alias"),
    (True, 4.1, 3.0, "wrong"),
    (True, None, 3.0, "wrong"),
])
def test_classify_outcome(passed, bls, true, want):
    assert ir.classify_outcome(passed, bls, true) == want


def test_passes_gates_matches_the_survey_rule():
    assert ir.passes_gates({"status": "OK", "depth_flagged_implausible": False})
    assert not ir.passes_gates({"status": "OK", "depth_flagged_implausible": True})
    assert not ir.passes_gates({"status": "TOO_FEW_POINTS", "depth_flagged_implausible": False})
    assert not ir.passes_gates({"status": "OK"})


def test_choose_stars_only_takes_unflagged_reliable_stars_and_is_seeded():
    n = 60
    manifest = pd.DataFrame({"TIC": range(1, n + 1), "Tmag": np.linspace(10, 15, n), "status": "OK",
                             "n_points": 5000, "author_used": "SPOC"})
    manifest.loc[0, "status"] = "NO_DATA"
    manifest.loc[1, "n_points"] = 10 ** 6
    vetting = pd.DataFrame({"TIC": range(1, n + 1), "status": "OK",
                            "depth_flagged_implausible": [True] * 5 + [False] * (n - 5)})
    # depth_flagged_implausible True means the star FAILS the gates, so TICs 1-5 are eligible
    edges = [11.0, 12.0, 13.0, 14.0]
    a = ir.choose_stars(manifest, vetting, edges, 3, seed=1)
    b = ir.choose_stars(manifest, vetting, edges, 3, seed=1)
    assert a.equals(b)
    assert (a.groupby("stratum").size() <= 3).all()
    assert 1 not in set(a.TIC) and 2 not in set(a.TIC)          # no data / too many points
    assert len(a) > 0 and set(a.TIC) <= {3, 4, 5}                # only failing, usable, small stars qualify


def test_report_counts_and_excludes_unsearchable_from_recall():
    rows = []
    base = {"tic": 1, "stratum": 0, "tmag": 12.0, "author": "SPOC", "n_points": 1000, "span_days": 27.0,
            "seed": 1, "t0": 1.0, "duration": 0.1, "ingress_frac": 0.5, "status": "OK", "bls_snr": 20.0, "n_eclipses": 5}
    # 4 searchable injections: 2 exact, 1 alias, 1 missed; 2 unsearchable (missed by construction)
    for k, (per, dep, out) in enumerate([(1.0, 0.01, "exact"), (3.0, 0.03, "exact"), (8.0, 0.2, "alias"), (12.0, 0.001, "missed")]):
        rows.append(dict(base, kind="inject", k=k, period=per, depth1=dep, depth2=0.0, searchable=True,
                         passed=out != "missed", bls_period=per, outcome=out))
    for k in range(4, 6):
        rows.append(dict(base, kind="inject", k=k, period=30.0, depth1=0.1, depth2=0.0, searchable=False,
                         passed=False, bls_period=None, outcome="missed"))
    for k in range(10):
        rows.append(dict(base, kind="shuffle", k=k, period=np.nan, depth1=np.nan, depth2=np.nan, searchable=True,
                         passed=(k == 0), bls_period=2.0, outcome="pass" if k == 0 else "clean"))
    res = pd.DataFrame(rows)
    rep = ir.build_report(res, now=datetime(2026, 11, 8, tzinfo=timezone.utc))
    assert rep["counts"]["injections"] == 6 and rep["counts"]["searchable_injections"] == 4
    assert rep["recall_overall"]["detected"]["k"] == 3 and rep["recall_overall"]["detected"]["n"] == 4
    assert rep["recall_overall"]["exact_period"]["k"] == 2
    assert rep["searchable_fraction"]["k"] == 4 and rep["searchable_fraction"]["n"] == 6
    assert rep["false_alarm_shuffle"]["k"] == 1 and rep["false_alarm_shuffle"]["n"] == 10
    by_p = {b["bin"]: b for b in rep["recall_by_period"]}
    assert by_p["<1 d"]["n"] == 0 and by_p["1-2 d"]["n"] == 1 and by_p[">10 d"]["detected"]["k"] == 0
    assert sum(b["n"] for b in rep["recall_by_period"]) == 4
    assert sum(b["n"] for b in rep["recall_by_depth"]) == 4


def test_end_to_end_a_deep_eclipse_is_recovered_and_flat_noise_is_not():
    """Real vetting function on a synthetic light curve (about 1 s of BLS)."""
    import f3i_vet as f3
    f3.make_plot = lambda *a, **k: None
    rng = np.random.default_rng(3)
    t = np.arange(0, 27.0, 0.01)
    flux = 1.0 + 0.002 * rng.normal(size=len(t))
    err = np.full_like(t, 0.002)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p = {"period": 2.37, "depth1": 0.08, "depth2": 0.03, "duration": 0.15, "ingress_frac": 0.5, "t0_frac": 0.3}
        f_inj, _ = ir.inject(flux, t, p, float(t.min()))
        pd.DataFrame({"time": t, "flux": f_inj, "flux_err": err}).to_csv(d / "a.csv", index=False)
        pd.DataFrame({"time": t, "flux": flux, "flux_err": err}).to_csv(d / "b.csv", index=False)
        ra = f3.process_one_star(1, d / "a.csv", d)
        rb = f3.process_one_star(2, d / "b.csv", d)
    assert ir.passes_gates(ra)
    assert ir.classify_outcome(True, ra["bls_period"], 2.37) in ("exact", "alias")
    assert not ir.passes_gates(rb)


def test_grid_size_scales_with_span_and_is_capped():
    assert ir.grid_size(15000, 20.0, 8) == 15000          # shorter than a sector: default
    assert ir.grid_size(15000, 56.0, 8) == 30000
    assert ir.grid_size(15000, 840.0, 8) == 15000 * 8     # capped
    assert ir.grid_size(15000, 840.0, 2) == 30000


def test_whatif_tag_is_empty_for_the_default_and_distinct_otherwise():
    from types import SimpleNamespace as NS
    assert ir.whatif_tag(NS(min_eclipses=None, period_grid_scale_max=None)) == ""
    assert ir.whatif_tag(NS(min_eclipses=2, period_grid_scale_max=None)) == "min2"
    assert ir.whatif_tag(NS(min_eclipses=None, period_grid_scale_max=8.0)) == "grid8"


def test_report_counts_misses_that_locked_onto_the_host_signal():
    rows = []
    for k, (bls, outcome) in enumerate([(2.0, "missed"), (10.0, "missed"), (4.0, "missed"), (5.0, "exact")]):
        rows.append({"tic": 1, "stratum": 0, "tmag": 12.0, "author": "X", "n_points": 100, "span_days": 20.0, "cadence_min": 30.0,
                     "kind": "inject", "k": k, "status": "OK", "passed": outcome != "missed", "bls_period": bls, "bls_snr": 9.0,
                     "n_eclipses": 3, "outcome": outcome, "period": 5.0, "depth1": 0.05, "duration": 0.1, "searchable": True})
    res = pd.DataFrame(rows).reindex(columns=ir.RESULT_COLUMNS)
    rep = ir.build_report(res, host_periods={1: 2.0})
    # host period 2.0: a miss at 2.0 (same) and 4.0 (double) lock on; 10.0 does not
    assert rep["missed_on_host_signal"]["k"] == 2 and rep["missed_on_host_signal"]["n"] == 3
    assert ir.build_report(res)["missed_on_host_signal"] is None


def test_choose_stars_can_restrict_to_quiet_hosts():
    manifest = pd.DataFrame({"TIC": [1, 2, 3, 4], "status": ["OK"] * 4, "n_points": [100] * 4, "Tmag": [12.0] * 4})
    vetting = pd.DataFrame({"TIC": [1, 2, 3, 4], "status": ["OK"] * 4, "depth_flagged_implausible": [True] * 4,
                            "bls_snr": [5.0, 40.0, 400.0, float("-inf")]})
    quiet = ir.choose_stars(manifest, vetting, [13.0], 10, max_host_snr=50.0)
    assert set(quiet["TIC"]) == {1, 2}                      # strong and non-finite hosts are excluded
    assert set(ir.choose_stars(manifest, vetting, [13.0], 10)["TIC"]) == {1, 2, 3, 4}
