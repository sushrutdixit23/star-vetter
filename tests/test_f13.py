"""
Tests for f13_ephemeris.py using synthetic light curves with a known answer.
No network. Run from the repo root:   py -m pytest tests -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import f13_ephemeris as f13  # noqa: E402

P_TRUE, T0_TRUE, DUR = 3.1234, 10.0, 0.15


def eclipse_profile(dt, dur=DUR, depth=0.08):
    """Trapezoid: flat bottom for |dt| < dur/4, linear ingress/egress to dur/2."""
    a = np.abs(dt)
    out = np.zeros_like(a)
    out[a < dur / 4] = depth
    ramp = (a >= dur / 4) & (a < dur / 2)
    out[ramp] = depth * (dur / 2 - a[ramp]) / (dur / 4)
    return out


def make_sectors(starts, drift_per_cycle2=0.0, noise=0.002, seed=1, length=25.0):
    """Concatenated light curve over several 'sectors'. drift_per_cycle2 adds a
    quadratic timing term (days per cycle^2) to mimic a changing period."""
    rng = np.random.default_rng(seed)
    t_all, f_all, e_all, s_all = [], [], [], []
    for k, st in enumerate(starts, start=1):
        t = np.arange(st, st + length, 10.0 / 1440)
        E = np.round((t - T0_TRUE) / P_TRUE)
        tc = T0_TRUE + E * P_TRUE + drift_per_cycle2 * E ** 2
        flux = 1.0 - eclipse_profile(t - tc) + rng.normal(0, noise, len(t))
        t_all.append(t)
        f_all.append(flux)
        e_all.append(np.full(len(t), noise))
        s_all.append(np.full(len(t), k))
    return (np.concatenate(t_all), np.concatenate(f_all),
            np.concatenate(e_all), np.concatenate(s_all))


def measured(starts, **kw):
    t, f, e, s = make_sectors(starts, **kw)
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE, DUR)
    assert tpl is not None
    return f13.measure_eclipses(t, f, e, s, P_TRUE, T0_TRUE, DUR, tpl)


STARTS = [10.0, 400.0, 800.0]


def test_recovers_known_period_within_its_error():
    ecl = measured(STARTS)
    assert len(ecl) >= 20
    fit = f13.fit_line([e["E"] for e in ecl], [e["T"] for e in ecl], [e["sigma"] for e in ecl])
    sigP = np.sqrt(fit["cov"][1, 1])
    assert abs(fit["P"] - P_TRUE) < 4 * sigP
    assert sigP < 1e-5            # three sectors over ~800 d pin P to well under a second
    assert fit["chi2_red"] < 3    # formal errors are about right


def test_single_eclipse_times_are_unbiased_and_errors_calibrated():
    ecl = measured(STARTS)
    truth = np.array([T0_TRUE + e["E"] * P_TRUE for e in ecl])
    z = (np.array([e["T"] for e in ecl]) - truth) / np.array([e["sigma"] for e in ecl])
    assert abs(np.mean(z)) < 0.5
    assert 0.5 < np.std(z) < 1.8


def test_holdout_passes_for_a_constant_period():
    rows = f13.leave_one_sector_out(measured(STARTS))
    assert len(rows) == 3
    assert f13.holdout_status(rows) == "PASS"
    assert min(r["p_value"] for r in rows) > f13.HOLDOUT_FAMILY_ALPHA / len(rows)


def test_holdout_catches_a_period_change():
    # quadratic term: the last sector drifts by roughly 30 minutes
    E_last = (STARTS[-1] - T0_TRUE) / P_TRUE
    c = (30.0 / 1440) / E_last ** 2
    rows = f13.leave_one_sector_out(measured(STARTS, drift_per_cycle2=c))
    assert f13.holdout_status(rows) == "FAIL"


def test_holdout_needs_more_than_one_sector():
    rows = f13.leave_one_sector_out(measured([10.0]))
    assert f13.holdout_status(rows) == "NOT_TESTABLE"


def test_prediction_error_grows_with_distance():
    ecl = measured(STARTS)
    fit = f13.fit_line([e["E"] for e in ecl], [e["T"] for e in ecl], [e["sigma"] for e in ecl])
    near_E = max(e["E"] for e in ecl) + 5
    far_E = near_E + 2000
    _, s_near = f13.predict(fit, [near_E])
    _, s_far = f13.predict(fit, [far_E])
    assert s_far[0] > s_near[0]


def test_predict_future_lists_eclipses_only_in_observed_sector_windows():
    ecl = measured(STARTS)
    fit = f13.fit_line([e["E"] for e in ecl], [e["T"] for e in ecl], [e["sigma"] for e in ecl])
    # shift the synthetic star's clock so cycle times land in 2026-27 BTJD (~4370-4800)
    fit = dict(fit)
    fit["T0"] = 4400.0
    fit["Eref"] = 0.0
    rows = f13.predict_future(fit, 123, 150.0, -20.0, [112])
    lo, hi, _ = f13.sector_window_btjd(112)
    assert rows, "expected at least one eclipse in the 26-day sector window"
    assert all(lo <= r["t_btjd"] <= hi and r["sector"] == 112 for r in rows)
    assert abs(len(rows) - (hi - lo) / P_TRUE) <= 1
    assert f13.predict_future(fit, 123, 150.0, -20.0, [60]) == []   # not a Year 9 sector


def test_utc_conversion_differs_from_naive_by_less_than_light_travel_time():
    from astropy.time import Time
    btjd = 4400.123456
    utc = f13.btjd_to_utc_iso(btjd, 150.0, -20.0)
    naive = Time(btjd + f13.BTJD_OFFSET, format="jd", scale="tdb").utc
    diff_s = abs((Time(utc, scale="utc") - naive).to("s").value)
    assert diff_s < 8.5 * 60 + 80   # light time across 1 AU is 499 s; plus TDB-UTC offset ~70 s


def test_correlated_errors_within_a_sector_are_not_overcounted():
    """The old statistic (mean z * sqrt(n)) false-failed this: one held-out
    sector with many eclipses and a modest, fully correlated prediction error."""
    fails = 0
    for seed in range(8):
        rows = f13.leave_one_sector_out(measured(STARTS, seed=seed))
        fails += f13.holdout_status(rows) == "FAIL"
    assert fails <= 1      # ~1% family-wise false-alarm rate; allow one in 8 for luck


def test_red_noise_adds_jitter_and_flags_excess_but_keeps_predictions_honest():
    """Smoothly wandering eclipse times (a third body, say): the fit must absorb
    it as jitter instead of clipping eclipses, and the held-out sectors must
    then be predicted within the inflated error."""
    rng = np.random.default_rng(5)
    t, f, e, s = make_sectors([10.0 + 40.0 * k for k in range(12)], length=15.0)
    # shift each sector's eclipses by a smooth +/-3 min sinusoid of sector number
    shifts = {k: 3.0 / 1440 * np.sin(2 * np.pi * k / 12) for k in range(1, 13)}
    t = t - np.array([shifts[int(x)] for x in s])
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE, DUR)
    ecl = f13.measure_eclipses(t, f, e, s, P_TRUE, T0_TRUE, DUR, tpl)
    E = np.array([x["E"] for x in ecl], float)
    T = np.array([x["T"] for x in ecl])
    S = np.array([x["sigma"] for x in ecl])
    G = np.array([x["sector"] for x in ecl])
    keep = f13.clip_outliers(E, T, S, G)
    assert keep.mean() > 0.9                       # wobble not clipped away
    fit = f13.fit_line(E[keep], T[keep], S[keep], G[keep])
    assert fit["jitter_mode"] == "sector"
    assert fit["jitter"] > f13.EXCESS_FACTOR * np.median(S)     # flagged TIMING_EXCESS
    rows = f13.leave_one_sector_out([x for x, k in zip(ecl, keep) if k])
    assert f13.holdout_status(rows) == "PASS"


# ---------------------------------------------------------------------------
# measurement robustness (added after real-data failures: partial eclipses and
# an interim ephemeris dragged by over-confident outliers)
# ---------------------------------------------------------------------------

def test_eclipse_covered_accepts_full_window_and_rejects_holes():
    cad = 10.0 / 1440
    d = np.arange(-2 * DUR, 2 * DUR, cad)
    assert f13.eclipse_covered(d, DUR)
    assert not f13.eclipse_covered(d[d < 0.3 * DUR], DUR)                 # egress missing
    assert not f13.eclipse_covered(d[(d < -0.1 * DUR) | (d > 0.5 * DUR)], DUR)   # hole across mid-eclipse


def test_uniformly_thinned_data_is_still_covered():
    cad = 30.0 / 1440                       # e.g. 30-minute FFI cadence, wide eclipse
    d = np.arange(-2 * DUR, 2 * DUR, cad)
    assert f13.eclipse_covered(d, DUR)


def test_eclipse_cut_by_a_data_gap_is_not_timed():
    t, f, e, s = make_sectors([10.0], length=40.0)
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE, DUR)
    full = f13.measure_eclipses(t, f, e, s, P_TRUE, T0_TRUE, DUR, tpl)
    E_cut = full[3]["E"]
    tc = T0_TRUE + E_cut * P_TRUE
    keep = ~((t > tc + 0.05 * DUR) & (t < tc + 3 * DUR))                  # remove egress and beyond
    cut = f13.measure_eclipses(t[keep], f[keep], e[keep], s[keep], P_TRUE, T0_TRUE, DUR, tpl)
    assert E_cut in {x["E"] for x in full}
    assert E_cut not in {x["E"] for x in cut}
    assert len(cut) >= len(full) - 2                                      # others untouched


def test_robust_line_ignores_confident_outliers_that_drag_weighted_fits():
    E = np.arange(0, 20, dtype=float)
    T = 100.0 + 2.5 * E + np.random.default_rng(3).normal(0, 0.001, 20)
    S = np.full(20, 0.002)
    for i, shift in ((15, 0.04), (17, -0.045)):        # two bad eclipses claiming tiny errors
        T[i] += shift
        S[i] = 0.0002
    W = 1.0 / S ** 2
    A = np.vstack([np.ones_like(E), E]).T
    plain = np.linalg.solve(A.T @ (A * W[:, None]), A.T @ (W * T))[1]
    jittered = f13.fit_line(E, T, S)["P"]
    robust = f13.robust_line(E, T)
    assert abs(plain - 2.5) > 1e-3                      # a plain weighted fit is badly dragged
    assert abs(robust["P"] - 2.5) < 1e-4                # the robust line is not
    assert abs(robust["P"] - 2.5) < abs(jittered - 2.5)  # and beats even the jitter-aware fit
    assert not robust["keep"][15] and not robust["keep"][17]


def test_robust_line_needs_two_distinct_cycles():
    assert f13.robust_line([1, 1, 1], [5.0, 5.001, 4.999]) is None


def _fake_lcs(starts, **kw):
    import lightkurve as lk
    t, f, e, s = make_sectors(starts, **kw)
    return [(int(k), lk.LightCurve(time=t[s == k], flux=f[s == k], flux_err=e[s == k]))
            for k in np.unique(s)]


def test_measure_star_recovers_from_a_period_that_is_off_by_6_minutes_per_cycle(monkeypatch):
    """Real failure: pipeline period off by ~0.004 d. Eclipses drift out of the
    nominal window; the interim ephemeris must still converge to the truth."""
    monkeypatch.setattr(f13, "load_or_fetch_lightcurves",
                        lambda tic, author, log, lc_dir=None: _fake_lcs([10.0, 40.0]))
    res = f13.measure_star(1, None, P_TRUE + 0.004, T0_TRUE, DUR, lambda *a: None)
    assert res["status"] == "OK" and res["measure_version"] == f13.MEASURE_VERSION
    assert abs(res["P_used"] - P_TRUE) < 3e-4
    ecl = res["eclipses"]
    assert len(ecl) >= 15
    fit = f13.fit_line([x["E"] for x in ecl], [x["T"] for x in ecl], [x["sigma"] for x in ecl])
    assert abs(fit["P"] - P_TRUE) < 5 * np.sqrt(fit["cov"][1, 1]) + 1e-6
    res_min = np.array([(x["T"] - (T0_TRUE + x["E"] * P_TRUE)) * 1440 for x in ecl])
    assert np.max(np.abs(res_min)) < 8.0                  # no saw-tooth, no wrapped eclipses


def test_light_curve_cache_round_trips_and_skips_the_download(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(tic, author, log):
        calls.append(tic)
        return _fake_lcs([10.0, 40.0])

    monkeypatch.setattr(f13, "fetch_sector_lightcurves", fake_fetch)
    first = f13.load_or_fetch_lightcurves(7, None, print, tmp_path)
    second = f13.load_or_fetch_lightcurves(7, None, print, tmp_path)
    assert calls == [7]                                   # downloaded once only
    assert [s for s, _ in first] == [s for s, _ in second]
    for (_, a), (_, b) in zip(first, second):
        assert np.allclose(a.time.value, b.time.value)
        assert np.allclose(a.flux.value, b.flux.value, atol=1e-6)


def test_cache_files_from_older_measurement_code_are_not_trusted():
    assert f13.MEASURE_VERSION >= 2


def test_symmetry_center_finds_the_middle_of_an_off_centre_eclipse():
    x = np.linspace(-2 * DUR, 2 * DUR, 200)
    for offset in (-0.4 * DUR, -0.1 * DUR, 0.0, 0.25 * DUR, 0.45 * DUR):
        y = 1.0 - eclipse_profile(x - offset)
        assert abs(f13.symmetry_center(x, y, DUR) - offset) < 0.01 * DUR


def test_template_zero_point_is_the_physical_eclipse_not_the_starting_epoch():
    """Start the search 40 minutes late. Eclipse times must still land on the
    true mid-eclipse, not inherit the starting epoch's error."""
    t, f, e, s = make_sectors([10.0, 40.0])
    late = 40.0 / 1440
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE + late, DUR)
    ecl = f13.measure_eclipses(t, f, e, s, P_TRUE, T0_TRUE + late, DUR, tpl)
    res = np.array([(x["T"] - (T0_TRUE + x["E"] * P_TRUE)) * 1440 for x in ecl])
    assert len(ecl) >= 15
    assert abs(np.median(res)) < 1.5, np.median(res)      # minutes


# ---------------------------------------------------------------------------
# phase connection across long gaps
# ---------------------------------------------------------------------------

def _patch_lcs(monkeypatch, starts, **kw):
    monkeypatch.setattr(f13, "load_or_fetch_lightcurves",
                        lambda tic, author, log, lc_dir=None: _fake_lcs(starts, **kw))


def _resid_min(ecl):
    return np.array([(x["T"] - (T0_TRUE + x["E"] * P_TRUE)) * 1440 for x in ecl])


def test_long_baseline_with_a_bls_grade_period_error_connects_every_sector(monkeypatch):
    """Period wrong by 6e-4 d (2e-4 relative): over 1,500 days (480 cycles) the
    nominal ephemeris is ~0.3 d off, two eclipse widths. Measuring each sector
    against it fails; connecting outward sector by sector must succeed."""
    _patch_lcs(monkeypatch, [10.0, 40.0, 400.0, 800.0, 1500.0])
    res = f13.measure_star(1, None, P_TRUE + 6e-4, T0_TRUE + 0.03, DUR, lambda *a: None)
    assert res["status"] == "OK"
    assert res["sectors_unconnected"] == [] and res["sectors_connected"] == [1, 2, 3, 4, 5]
    ecl = res["eclipses"]
    assert {x["sector"] for x in ecl} == {1, 2, 3, 4, 5}
    assert np.max(np.abs(_resid_min(ecl))) < 6.0
    assert abs(res["P_used"] - P_TRUE) < 2e-6


def test_a_sector_too_far_to_connect_is_reported_not_guessed(monkeypatch):
    """~9,500 cycles away the period error cannot be bridged unambiguously."""
    _patch_lcs(monkeypatch, [10.0, 40.0, 30000.0])
    res = f13.measure_star(1, None, P_TRUE + 3e-3, T0_TRUE, DUR, lambda *a: None)
    assert res["status"] == "OK"
    assert res["sectors_unconnected"] == [3]
    assert {x["sector"] for x in res["eclipses"]} == {1, 2}


def test_noise_only_sector_gives_no_eclipses():
    t, f, e, s = make_sectors([10.0], noise=0.002)
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE, DUR)
    flat = 1.0 + np.random.default_rng(5).normal(0, 0.002, len(t))
    assert f13.measure_eclipses(t, flat, e, s, P_TRUE, T0_TRUE, DUR, tpl) == []


def test_sector_without_eclipses_is_not_connected_to_noise(monkeypatch):
    lcs = _fake_lcs([10.0, 40.0, 80.0])
    import lightkurve as lk
    s3, lc3 = lcs[2]
    rng = np.random.default_rng(9)
    lcs[2] = (s3, lk.LightCurve(time=lc3.time.value, flux=1.0 + rng.normal(0, 0.002, len(lc3)),
                                flux_err=lc3.flux_err.value))
    monkeypatch.setattr(f13, "load_or_fetch_lightcurves", lambda *a, **k: lcs)
    res = f13.measure_star(1, None, P_TRUE + 3e-4, T0_TRUE, DUR, lambda *a: None)
    assert res["status"] == "OK" and 3 in res["sectors_unconnected"]
    assert {x["sector"] for x in res["eclipses"]} <= {1, 2}


def test_predicted_sigma_grows_with_distance_and_has_a_prior_fallback():
    ecl = [{"E": i, "T": T0_TRUE + i * P_TRUE, "sigma": 1e-3, "sector": 1} for i in range(8)]
    near, _ = f13.predicted_sigma(ecl, 20, P_TRUE, DUR)
    far, _ = f13.predicted_sigma(ecl, 2000, P_TRUE, DUR)
    assert far > 10 * near
    two = ecl[:2]
    sig, fit = f13.predicted_sigma(two, 500, P_TRUE, DUR)
    assert fit is None and sig > 0.1 * DUR


def test_connection_threshold_guards_against_cycle_slips():
    assert f13.connectable(0.20, P_TRUE)        # 4 sigma = 0.80 d <= 0.35 * 3.12 d
    assert not f13.connectable(0.30, P_TRUE)    # 4 sigma = 1.20 d >  1.09 d
    assert not f13.connectable(P_TRUE / 2, P_TRUE)


def test_scan_finds_eclipses_far_outside_the_normal_search_window():
    """Prediction wrong by 0.6 d (four eclipse widths): the +/-0.75 duration
    window cannot see them, the scan must."""
    t, f, e, s = make_sectors([10.0], length=40.0)
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE, DUR)
    for wrong in (-0.6, 0.45, 0.9):
        delta = f13.scan_offset(t, f, e, P_TRUE, T0_TRUE + wrong, DUR, tpl, span=1.2)
        assert delta is not None and abs(delta - (-wrong)) < 0.5 * DUR, (wrong, delta)


def test_scan_refuses_noise_and_ambiguous_sectors():
    t, f, e, s = make_sectors([10.0], length=40.0)
    tpl = f13.build_template(t, f, P_TRUE, T0_TRUE, DUR)
    flat = 1.0 + np.random.default_rng(4).normal(0, 0.002, len(t))
    assert f13.scan_offset(t, flat, e, P_TRUE, T0_TRUE, DUR, tpl, span=1.0) is None
    # a window of a whole period or more contains every eclipse twice: no unique answer
    assert f13.scan_offset(t, f, e, P_TRUE, T0_TRUE, DUR, tpl, span=0.5 * P_TRUE) is None
    assert f13.scan_offset(t, f, e, P_TRUE, T0_TRUE, DUR, tpl, span=1.2 * P_TRUE) is None
    # and the same data with a legitimate window is found (guards against an always-None scan)
    assert f13.scan_offset(t, f, e, P_TRUE, T0_TRUE + 0.3, DUR, tpl, span=0.6) is not None


def test_scan_connects_a_sector_that_direct_extrapolation_cannot_reach(monkeypatch):
    """One sector pins the period only to ~1e-4 d; 320 cycles later the
    eclipse is ~0.1-0.2 d from where the ephemeris puts it, beyond the +/-0.75
    duration window but far inside half a period."""
    _patch_lcs(monkeypatch, [10.0, 1010.0])
    res = f13.measure_star(1, None, P_TRUE + 4e-4, T0_TRUE + 0.02, DUR, lambda *a: None)
    assert res["status"] == "OK" and res["sectors_unconnected"] == []
    r = _resid_min(res["eclipses"])
    assert {x["sector"] for x in res["eclipses"]} == {1, 2}
    assert np.max(np.abs(r)) < 6.0, np.max(np.abs(r))
    assert abs(res["P_used"] - P_TRUE) < 1e-6


# ---- grading: a pass over a short distance does not validate a long extrapolation ----

def _ho_rows(lags_forward, lags_back=(), sigma=1.0):
    return ([{"lag_days": float(l), "forward": True, "pred_sigma_min_mean": sigma} for l in lags_forward]
            + [{"lag_days": float(l), "forward": False, "pred_sigma_min_mean": sigma} for l in lags_back])


def test_holdout_rows_record_the_distance_they_tested():
    rows = f13.leave_one_sector_out(measured(STARTS))        # sectors 1, 2, 3 at t = 10, 400, 800
    by = {r["sector"]: r for r in rows}
    assert by[3]["forward"] and not by[1]["forward"] and not by[2]["forward"]
    assert 350 < by[3]["lag_days"] < 450                       # sector 3 is ~400 d after sector 2
    assert 350 < by[1]["lag_days"] < 450


def test_validated_needs_the_prediction_horizon_close_to_the_tested_distance():
    rows = _ho_rows([400.0])
    near = f13.prediction_grade("PASS", rows, 1000.0)          # 2.5x
    far = f13.prediction_grade("PASS", rows, 1300.0)           # 3.25x
    assert near["grade"] == "VALIDATED"
    assert far["grade"] == "UNVALIDATED" and "farther than tested" in far["note"]
    assert abs(far["extrapolation_factor"] - 3.25) < 1e-9


def test_a_short_pass_does_not_validate_a_four_year_prediction():
    g = f13.prediction_grade("PASS", _ho_rows([27.0]), 1500.0)
    assert g["grade"] == "UNVALIDATED" and g["extrapolation_factor"] > 50


def test_failed_holdout_is_rejected_whatever_the_horizon():
    assert f13.prediction_grade("FAIL", _ho_rows([400.0]), 10.0)["grade"] == "REJECTED"


def test_untestable_is_unvalidated_and_never_crashes_on_empty_input():
    for st in ("NOT_TESTABLE", "anything-else"):
        g = f13.prediction_grade(st, [], 500.0)
        assert g["grade"] == "UNVALIDATED" and g["tested_lag_days"] is None
    assert f13.prediction_grade("PASS", _ho_rows([400.0]), None)["grade"] == "UNVALIDATED"


def test_only_forward_holdouts_count_as_extrapolation_tested():
    g = f13.prediction_grade("PASS", _ho_rows([30.0], lags_back=[900.0]), 100.0)
    assert g["tested_lag_days"] == 30.0                         # a gap filled from both sides is not a forecast


# ---- rolling-origin forecast test ----

def test_rolling_origin_trains_on_early_sectors_and_predicts_all_later_ones():
    ecl = measured([10.0, 40.0, 400.0, 430.0, 460.0])
    rows = f13.rolling_origin(ecl)
    assert [r["train_sectors"] for r in rows] == [1, 2, 3]            # k = n-1 is the leave-one-out
    assert all(r["forward"] and r["kind"] == "rolling" for r in rows)
    assert rows[0]["lag_days"] > 440                                    # trained on sector 1, reached sector 5
    assert rows[0]["n_eclipses"] > rows[2]["n_eclipses"]
    assert f13.holdout_status(rows + f13.leave_one_sector_out(ecl)) == "PASS"


def test_rolling_origin_has_nothing_to_do_with_two_sectors():
    assert f13.rolling_origin(measured([10.0, 400.0])) == []


def test_rolling_origin_catches_drift_that_adjacent_sectors_hide():
    """Timing curvature that a linear fit hides over short lags but that ruins a
    forecast made from the first two sectors."""
    ecl = measured([10.0, 40.0, 400.0, 430.0, 460.0], drift_per_cycle2=2e-6)
    rolling = f13.rolling_origin(ecl)
    thresh = f13.HOLDOUT_FAMILY_ALPHA / (len(rolling) + 5)
    assert min(r["p_value"] for r in rolling) < thresh
    assert f13.holdout_status(rolling + f13.leave_one_sector_out(ecl)) == "FAIL"


def test_a_coarse_test_cannot_validate_a_precise_prediction():
    """A hold-out good to +/-1000 minutes passes whatever the clock does."""
    coarse = [{"lag_days": 1800.0, "forward": True, "pred_sigma_min_mean": 1100.0}]
    fine = [{"lag_days": 700.0, "forward": True, "pred_sigma_min_mean": 4.0}]
    g = f13.prediction_grade("PASS", coarse + fine, 1000.0, sigma_pub_min=4.0)
    assert g["tested_lag_days"] == 700.0 and g["grade"] == "VALIDATED"       # only the precise test counts
    g2 = f13.prediction_grade("PASS", coarse, 1000.0, sigma_pub_min=4.0)
    assert g2["grade"] == "UNVALIDATED" and "precise enough" in g2["note"]
    g3 = f13.prediction_grade("PASS", coarse, 1000.0, sigma_pub_min=900.0)    # a coarse prediction is fairly tested by it
    assert g3["grade"] == "VALIDATED"
