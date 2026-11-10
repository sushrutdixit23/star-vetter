import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f21_gaia_dr4_ready as g  # noqa: E402


def test_timing_error_grows_with_distance_from_the_reference_epoch():
    near = g.timing_error_at(58000.0, 3.0, 1e-6, 58000.0, 1e-3)
    far = g.timing_error_at(58000.0 + 3000.0, 3.0, 1e-6, 58000.0, 1e-3)
    assert near == pytest.approx(1e-3) and far == pytest.approx(np.hypot(1e-3, 1000 * 1e-6))


def test_testable_requires_a_precise_ephemeris_and_enough_in_eclipse_points():
    t0_btjd = 2300.0                          # about 2018.8: the Gaia window ends about 800-1100 days before this
    good, info = g.gaia_testable(3.0, 1e-6, t0_btjd, 1.0, 0.15)
    assert good and info["expected_in_eclipse_points"] == pytest.approx(70 * 0.05)
    bad, _ = g.gaia_testable(3.0, 5e-5, t0_btjd, 1.0, 0.15)           # 5e-5 d per cycle over ~1000 cycles: 0.05 d at the far end
    assert not bad
    short, _ = g.gaia_testable(30.0, 1e-6, t0_btjd, 1.0, 0.05)        # 70 * 0.05/30 = 0.1 points: nothing to test
    assert not short


def _gaia_like(n=70, depth=0.0, sigma=0.01, P=3.0, dur=0.15, seed=0):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(g.GAIA_DR4_START_MJD, g.GAIA_DR4_END_MJD, n))
    t0 = 57000.123
    f = 1.0 + rng.normal(0, sigma, n)
    ph = ((t - t0) / P + 0.5) % 1.0 - 0.5
    f[np.abs(ph) <= 0.5 * dur / P] -= depth
    return t, f, np.full(n, sigma), P, t0, dur


def test_fixed_ephemeris_fold_sees_a_deep_eclipse_and_not_noise():
    # many points so that a handful fall in eclipse
    t, f, e, P, t0, dur = _gaia_like(n=1200, depth=0.08)
    hit = g.fold_test(t, f, e, P, t0, dur)
    assert hit["n_in"] >= 20 and hit["z"] > 8 and hit["p_value"] < 0.01
    t, f, e, P, t0, dur = _gaia_like(n=1200, depth=0.0, seed=4)
    miss = g.fold_test(t, f, e, P, t0, dur)
    assert miss["p_value"] > 0.05 and abs(miss["z"]) < 4


def test_fold_reports_nothing_when_no_points_fall_in_eclipse():
    t = np.array([58000.0, 58001.5, 58002.7, 58003.1, 58004.4, 58005.9, 58006.2])
    r = g.fold_test(t, np.ones(7), np.full(7, 0.01), 3.0, 58000.75, 0.05)
    assert r["depth"] is None and r["p_value"] is None


def test_loader_is_explicitly_not_implemented():
    with pytest.raises(NotImplementedError):
        g.load_epoch_photometry(1)
