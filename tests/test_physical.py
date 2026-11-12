import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f28_physical as f28  # noqa: E402
import f25_gaia_dr4_run as f25  # noqa: E402


def test_mass_function_matches_the_standard_constant():
    # f(M) = 1.0361e-7 (1 - e^2)^1.5 K^3 P  [Msun, K in km/s, P in days]
    for k, p, e in ((30.0, 10.0, 0.0), (52.0, 14.28, 0.2), (5.0, 3.1, 0.5)):
        assert f28.mass_function(k, p, e) == pytest.approx(1.0361e-7 * (1 - e * e) ** 1.5 * k ** 3 * p, rel=2e-3)


def test_companion_mass_inverts_the_mass_function():
    fm = f28.mass_function(40.0, 6.0, 0.0)
    m2 = f28.min_companion_mass(fm, 1.1)
    assert m2 ** 3 / (1.1 + m2) ** 2 == pytest.approx(fm, rel=1e-6)


def test_total_mass_from_kepler_gives_one_solar_mass_at_one_au():
    assert f28.total_mass(215.032, 365.25) == pytest.approx(1.0, rel=2e-3)


def test_rv_convention_primary_eclipse_and_fit_recovery():
    P, t0, e, w = 7.3, 2459000.0, 0.3, np.radians(40.0)
    # at primary eclipse the star-1 velocity is gamma + K e cos(omega)
    assert f28.rv_shape([t0], P, t0, e, w)[0] == pytest.approx(e * np.cos(w), abs=1e-9)
    rng = np.random.default_rng(1)
    t = t0 + rng.uniform(0, 400, 12)
    v = 12.0 + 45.0 * f28.rv_shape(t, P, t0, e, w) + rng.normal(0, 0.5, t.size)
    r = f28.fit_k_gamma(t, v, np.full(t.size, 0.5), P, t0, e, w)
    assert r["k1_kms"] == pytest.approx(45.0, abs=1.0) and r["gamma_kms"] == pytest.approx(12.0, abs=0.5)
    assert r["chi2"] < 3 * r["dof"] and r["chi2_constant"] > 100 * r["chi2"]


def test_gaia_amplitude_limits_are_conservative():
    # pure noise at G_RVS 11 (sigma 3 km/s): a range of 12 km/s gives no lower limit
    klo, _ = f28.k_lower_from_amplitude(12.0, 11.0)
    assert klo == 0.0
    klo, _ = f28.k_lower_from_amplitude(100.0, 11.0)
    assert 40.0 < klo < 50.0
    kup = f28.k_upper_from_amplitude(2.0, 9.5, 25)
    assert kup is not None and kup > 1.0
    assert f28.k_upper_from_amplitude(2.0, 9.5, 5) is None        # too few transits for an upper limit


def test_dr4_rv_rule_moves_static_and_twin():
    rng = np.random.default_rng(3)
    P = 4.2
    t = np.sort(rng.uniform(57000, 58800, 30))
    v = 30.0 * np.sin(2 * np.pi * t / P + 0.7) + rng.normal(0, 1.0, t.size)
    fit = f25.rv_sinusoid(t, v, np.full(t.size, 1.0), P)
    assert fit["k_kms"] == pytest.approx(30.0, abs=1.5)
    assert f25.rv_decide(fit, P, 1.0, 0.1)[0] == "MOVES"
    v0 = rng.normal(0, 0.3, t.size)
    fit0 = f25.rv_sinusoid(t, v0, np.full(t.size, 0.3), P)
    assert f25.rv_decide(fit0, P, 1.0, 0.10, 0.05)[0] == "BLEND_INDICATED"
    assert f25.rv_decide(fit0, P, 1.0, 0.10, 0.9)[0] == "STATIC_OR_TWIN"
    assert f25.rv_decide(fit0, P, 1.0, 0.002, 0.05)[0] == "SUBSTELLAR_OR_BLEND"


def test_dr4_rv_reader_accepts_dr3_style_times():
    import pandas as pd
    t_mjd = np.array([57100.0, 57300.0, 57900.0])
    df = pd.DataFrame({"rv_obs_time": t_mjd - (2455197.5 - 2400000.5), "radial_velocity": [1.0, 2.0, 3.0],
                       "radial_velocity_error": [0.5, 0.5, 0.5]})
    t, v, e = f25.rv_epoch_arrays(df)
    assert np.allclose(t, t_mjd) and list(v) == [1.0, 2.0, 3.0]


def test_orbit_check_handles_outer_orbits_and_missing_omega():
    outer = f28.orbit_check({"period": 630.0, "eccentricity": 0.6, "eccentricity_error": 0.06, "arg_periastron": None,
                             "nss_solution_type": "Orbital"}, 0.68, {"e": None, "ecosw": -0.004})
    assert outer["outer_orbit"] and not outer["same_period"] and outer["gaia_ecosw"] is None
    inner = f28.orbit_check({"period": 11.5393, "eccentricity": 0.235, "eccentricity_error": 0.038, "arg_periastron": 321.2,
                             "semi_amplitude_primary": 38.3, "nss_solution_type": "SB1"}, 11.540, {"e": None, "ecosw": 0.210})
    assert inner["same_period"] and not inner["outer_orbit"]
    assert inner["gaia_ecosw"] == pytest.approx(0.183, abs=0.002)
    assert inner["ecosw_difference_sigma"] < 1.0


ellc = pytest.importorskip("ellc")
emcee = pytest.importorskip("emcee")
import f26_ebfit as f26  # noqa: E402


def _synthetic(period=3.7, rsum=0.18, k=0.8, incl=87.5, J=0.6, e=0.12, w_deg=70.0, l3=0.0, cadence_min=10, noise=8e-4, seed=2):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, 26.0, cadence_min / 1440.0) + 1500.0
    p = {"rsum": rsum, "k": k, "cosi": np.cos(np.radians(incl)), "J": J, "fc": np.sqrt(e) * np.cos(np.radians(w_deg)),
         "fs": np.sqrt(e) * np.sin(np.radians(w_deg)), "l3": l3, "u1": 0.4, "u1b": 0.4, "t0": 1501.0, "dP": 0.0}
    f = f26.ellc_lc(t, p, period, cadence_min / 1440.0, int(np.ceil(cadence_min / 3.0)))
    f = f * (1 + 0.002 * np.sin(2 * np.pi * (t - t[0]) / 9.0)) + rng.normal(0, noise, t.size)   # slow trend + noise
    return t, f, np.full(t.size, 1), p


def test_model_duration_matches_the_light_curve():
    t, f, s, p = _synthetic(noise=0.0)
    theta = np.array([0.0, p["rsum"], p["k"], p["cosi"], p["J"], p["fc"], p["fs"], 0.0, 0.4, 0.4, 0.0])
    tt = np.linspace(p["t0"] - 0.5, p["t0"] + 3.7 - 0.5, 40000)
    m = f26.ellc_lc(tt, p, 3.7)
    inside = m < 1 - 1e-6
    edges = tt[np.where(np.diff(inside.astype(int)) != 0)[0]]
    longest = max(edges[1] - edges[0], edges[3] - edges[2])
    assert f26.model_duration(theta, 3.7) == pytest.approx(longest, rel=0.03)


def test_local_detrend_drops_one_sided_eclipses():
    t, f, s, p = _synthetic(noise=0.0)
    keep = ~((t > 1501.0 - 0.45) & (t < 1501.0 - 0.13))      # first primary loses its left baseline only
    td, fd, sd = f26.detrend_local(t[keep], f[keep], 3.7, 1501.0, 0.25, 0.5, s[keep])
    assert not np.any(np.abs(td - 1501.0) < 0.05)              # that eclipse is dropped ...
    assert np.any(np.abs(td - (1501.0 + 3.7)) < 0.05)          # ... the next one is kept


def test_fit_recovers_an_injected_eccentric_binary():
    t, f, s, p = _synthetic()
    ecosw = 0.12 * np.cos(np.radians(70.0))
    res = f26.fit_star(t, f, s, 3.7, 1501.0, 0.2, ecosw, 0.5, steps=60)
    assert res["status"] == "OK"
    q = res["params"]
    assert q["e"]["median"] == pytest.approx(0.12, abs=0.03)
    assert q["ecosw"]["median"] == pytest.approx(ecosw, abs=0.004)
    assert q["incl"]["median"] == pytest.approx(87.5, abs=1.0)
    r1 = 0.18 / 1.8
    assert q["r1"]["median"] == pytest.approx(r1, rel=0.1)

