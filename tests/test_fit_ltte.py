import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fit_ltte  # noqa: E402


def synth(P3_years=10.0, amp_min=30.0, period_days=14.8, n=30, span_cycles=140, seed=3, err=2.0):
    rng = np.random.default_rng(seed)
    E = np.sort(rng.uniform(0, span_cycles, n))
    t = E * period_days / 365.25
    y = 3.0 + 0.2 * E + amp_min * np.sin(2 * np.pi * t / P3_years + 0.7) + rng.normal(0, err, n)
    return [{"epoch": float(e), "oc_min": float(v), "err_min": err} for e, v in zip(E, y)]


def test_mass_function_is_keplers_third_law():
    # 1 AU orbit, 1 year: f = 1 solar mass
    assert fit_ltte.mass_function(1.0, 1.0) == pytest.approx(1.0)


def test_min_third_mass_inverts_the_mass_function():
    m3 = 0.5
    f = m3 ** 3 / (1.1 + m3) ** 2
    assert fit_ltte.min_third_mass(f, 1.1) == pytest.approx(m3, rel=1e-3)


def test_injected_light_travel_time_orbit_is_recovered_inside_the_allowed_range():
    g = synth(P3_years=10.0, amp_min=30.0)
    grid = np.exp(np.linspace(np.log(3.0), np.log(400.0), 240))
    rows, _ = fit_ltte.fit(g, 14.8, grid)
    s = fit_ltte.summarise(rows, fit_ltte.parabola_chi2(g), len(g))
    lo, hi = s["allowed_p3_years"]
    assert lo <= 10.0 <= hi
    # the injected amplitude gives a12 sin i; its minimum mass must be inside the reported range
    true_a = 30.0 * 60.0 / 86400.0 * fit_ltte.C_AU_PER_DAY
    true_m = fit_ltte.min_third_mass(fit_ltte.mass_function(true_a, 10.0), 1.1)
    assert s["m3_min_msun_range"][0] * 0.5 <= true_m <= s["m3_min_msun_range"][1] * 1.5


def test_a_pure_parabola_is_not_claimed_to_need_a_third_body():
    rng = np.random.default_rng(4)
    E = np.sort(rng.uniform(0, 140, 30))
    y = 0.003 * E ** 2 - 0.3 * E + rng.normal(0, 2.0, 30)
    g = [{"epoch": float(e), "oc_min": float(v), "err_min": 2.0} for e, v in zip(E, y)]
    grid = np.exp(np.linspace(np.log(3.0), np.log(400.0), 240))
    rows, _ = fit_ltte.fit(g, 14.8, grid)
    s = fit_ltte.summarise(rows, fit_ltte.parabola_chi2(g), len(g))
    assert s["best_chi2"] > s["chi2_parabola"] - 6.0     # two extra parameters buy no large improvement
