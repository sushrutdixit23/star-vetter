import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f17_ztf_independent as z  # noqa: E402


def _series(n=900, span=1500.0, sigma=0.01, seed=0):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(58000, 58000 + span, n))
    return t, 1.0 + rng.normal(0, sigma, n), np.full(n, sigma)


def test_wilson_bounds():
    w = z.wilson(0, 10)
    assert w["lo"] == 0.0 and 0.0 < w["hi"] < 0.4
    assert z.wilson(5, 0)["rate"] is None


def test_select_same_star_drops_a_neighbour_object():
    rows = []
    for oid, ra, dec, n in ((1, 10.0, 20.0, 5), (2, 10.0 + 0.2 / 3600, 20.0, 5), (3, 10.0 + 2.5 / 3600, 20.0, 5)):
        for k in range(n):
            rows.append({"oid": oid, "ra": ra, "dec": dec, "mag": 15.0, "magerr": 0.02, "catflags": 0, "mjd": 58000 + k, "filtercode": "zg"})
    kept = z.select_same_star(pd.DataFrame(rows), 10.0, 20.0)
    assert set(kept["oid"]) == {1, 2}                      # field-overlap duplicate kept, 2.5 arcsec neighbour dropped
    assert len(z.select_same_star(pd.DataFrame(columns=["oid", "ra", "dec"]), 1.0, 1.0)) == 0


def test_relative_flux_pools_filters_and_drops_flagged_points():
    rng = np.random.default_rng(1)
    rows = []
    for fc, base in (("zg", 16.0), ("zr", 15.0)):
        for k in range(60):
            rows.append({"oid": 1, "mjd": 58000 + k + (0.5 if fc == "zr" else 0), "mag": base + rng.normal(0, 0.02), "magerr": 0.02,
                         "catflags": 0 if k else 1, "filtercode": fc})
    t, f, e = z.to_relative_flux(pd.DataFrame(rows))
    assert len(t) == 118 and abs(np.median(f) - 1.0) < 0.01 and np.all(np.diff(t) >= 0)   # 2 flagged points dropped, both filters near 1


def test_bright_outliers_are_clipped_but_dips_are_kept():
    rows = [{"oid": 1, "mjd": 58000 + k, "mag": 15.0, "magerr": 0.02, "catflags": 0, "filtercode": "zg"} for k in range(100)]
    rows[10]["mag"] = 13.0      # much brighter
    rows[20]["mag"] = 17.0      # much fainter: a possible eclipse
    t, f, e = z.to_relative_flux(pd.DataFrame(rows))
    assert f.max() < 1.1 and f.min() < 0.3


def test_control_periods_avoid_harmonics_and_respect_the_span():
    c = z.control_periods(3.0, 100, np.random.default_rng(0), span=2000.0)
    r = c / 3.0
    harmonics = np.array([a / b for a in range(1, 5) for b in range(1, 5)])
    assert len(c) == 100
    assert all(np.min(np.abs(x / harmonics - 1)) >= z.HARMONIC_EXCLUSION for x in r)
    assert c.min() >= 0.2 and (c * 3 <= 2000.0).all()


def test_period_window_has_bounded_drift():
    p = z.period_window(3.0, 0.12, 2000.0)
    step = np.diff(p).max()
    assert step * 2000.0 / 3.0 <= 0.12 / 5 * 1.05           # drift across the baseline stays under a fifth of the duration
    assert p.min() < 3.0 < p.max()


def test_injected_eclipse_is_recovered_and_noise_is_not():
    t, f, e = _series(seed=3)
    P, dur, depth = 3.1105, 0.12, 0.06
    g = z.inject_box(t, f, P * 1.0007, t.min() + 0.9, dur, depth)    # period 0.07 percent off the one given
    hit = z.assess(t, g, e, P, dur, depth, tic=1, n_controls=120, n_injections=8)
    miss = z.assess(t, f, e, P, dur, depth, tic=2, n_controls=120, n_injections=8)
    assert z.verdict(hit) == "CONFIRMED" and hit["p_value"] < 0.02 and 0.5 < hit["depth_ratio"] < 1.6
    assert z.verdict(miss) in ("NOT_SEEN", "INCONCLUSIVE") and miss["p_value"] > 0.02
    assert abs(hit["obs"]["period"] / (P * 1.0007) - 1) < 3e-4


def test_a_star_too_noisy_for_the_depth_is_inconclusive_not_not_seen():
    t, f, e = _series(n=300, sigma=0.08, seed=5)
    r = z.assess(t, f, e, 3.1105, 0.12, 0.01, tic=3, n_controls=120, n_injections=10)
    assert r["power"] < z.POWER_TESTABLE and z.verdict(r) == "INCONCLUSIVE"


def test_verdict_logic():
    ok = {"obs": {"n_events": 5, "snr": 9.0}, "p_value": 0.003, "depth_ratio": 1.0, "depth_ratio_err": 0.1, "power": 0.9}
    assert z.verdict(ok) == "CONFIRMED"
    assert z.verdict(dict(ok, p_value=0.2)) == "NOT_SEEN"                               # testable, not seen
    assert z.verdict(dict(ok, p_value=0.2, power=0.1)) == "INCONCLUSIVE"
    assert z.verdict(dict(ok, depth_ratio=8.0)) != "CONFIRMED"                          # depth far too large for the TESS eclipse
    assert z.verdict(dict(ok, obs={"n_events": 1, "snr": 9.0})) != "CONFIRMED"          # single epoch
    assert z.verdict(None) == "NO_DATA"


def test_odd_even_flags_half_period_and_secondary_is_found():
    t, f, e = _series(n=2500, span=900.0, sigma=0.01, seed=9)
    P, dur = 2.0, 0.1
    g = f.copy()
    cyc = np.round((t - t.min()) / P).astype(int)
    ph = ((t - t.min() + 0.5 * P) % P) - 0.5 * P
    g[(np.abs(ph) <= dur / 2) & (cyc % 2 == 0)] *= 0.90    # even eclipses deep
    g[(np.abs(ph) <= dur / 2) & (cyc % 2 == 1)] *= 0.98    # odd eclipses shallow
    oe = z.odd_even(t, g, e, P, t.min(), dur)
    assert oe is not None and abs(oe["z"]) > 5
    h = f.copy()
    ph2 = ((t - t.min()) / P) % 1.0
    h[np.abs(ph2 - 0.5) <= 0.4 * dur / P] *= 0.93
    sec = z.secondary(t, h, e, P, t.min(), dur)
    assert sec is not None and sec["z"] > 5


def test_summarise_counts_and_testable_fraction():
    stars = [{"status": s, "tier": "CLEAN"} for s in ["CONFIRMED"] * 3 + ["NOT_SEEN"] * 1 + ["INCONCLUSIVE"] * 2 + ["NO_DATA"] * 4]
    s = z.summarise(stars)
    assert s["stars"] == 10 and s["testable"] == 4 and s["confirmed_among_testable"]["k"] == 3
    assert s["confirmed_among_with_data"]["n"] == 6


def test_control_periods_leave_room_for_the_box():
    c = z.control_periods(1.05, 100, np.random.default_rng(0), span=2000.0, min_period=1.01 * 0.5)
    assert c.min() >= 0.505
