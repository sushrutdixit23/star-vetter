"""Noise model v2 of the eclipse fitter (f26_ebfit.py, --noise v2).

These tests check the pieces the injection-recovery study relies on: that integrating the baseline out of the
likelihood is the same as integrating it numerically, that the fast template model agrees with a direct ellc call,
that event cutting keeps the rules of the v1 detrending, and that v1 stays the default."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ellc = pytest.importorskip("ellc")
emcee = pytest.importorskip("emcee")
import f26_ebfit as f26  # noqa: E402

PERIOD = 3.7


def _params(**kw):
    p = {"rsum": 0.18, "k": 0.8, "cosi": float(np.cos(np.radians(87.5))), "J": 0.6, "fc": np.sqrt(0.12) * np.cos(np.radians(70.0)),
         "fs": np.sqrt(0.12) * np.sin(np.radians(70.0)), "l3": 0.0, "u1": 0.4, "u1b": 0.4, "t0": 1501.0, "dP": 0.0}
    p.update(kw)
    return p


def _lightcurve(cadence_min=10.0, noise=8e-4, seed=2, days=26.0, **kw):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence_min / 1440.0) + 1500.0
    p = _params(**kw)
    f = f26.ellc_lc(t, p, PERIOD, cadence_min / 1440.0, int(np.ceil(cadence_min / 3.0)))
    f = f * (1 + 0.002 * np.sin(2 * np.pi * (t - t[0]) / 9.0)) + rng.normal(0, noise, t.size)
    return t, f, np.full(t.size, 1), p


def _sec_phase(p):
    e = p["fc"] ** 2 + p["fs"] ** 2
    return (0.5 + 2.0 * e * np.cos(np.arctan2(p["fs"], p["fc"])) / np.pi) % 1.0


def _groups(cadence_min=10.0, noise=8e-4, duration=0.25, gp=True, **kw):
    t, f, s, p = _lightcurve(cadence_min=cadence_min, noise=noise, **kw)
    ev = f26.cut_events(t, f, s, PERIOD, p["t0"], duration, _sec_phase(p))
    return f26.event_groups(ev, duration, gp=gp), ev, p, (t, f, s)


def _theta(p, groups, lna=-9.0, lnrho=-1.5):
    base = [0.0, p["rsum"], p["k"], p["cosi"], p["J"], p["fc"], p["fs"], p["l3"], p["u1"], p["u1b"], 0.0]
    return np.array(base + [0.0] * groups[0]["n_white"] + ([lna, lnrho] if groups[0]["gp"] else []))


def test_v1_is_still_the_default_noise_model():
    assert f26.NOISE_DEFAULT == "v1"
    with pytest.raises(ValueError):
        f26.fit_star(*_lightcurve()[:3], PERIOD, 1501.0, 0.25, 0.0, 0.5, steps=5, noise="v3")


def test_baseline_marginalisation_equals_numerical_integration():
    """ln L(model) from the closed form must differ between two models exactly as a brute-force integral over the two
    baseline coefficients does (the constant p ln 2 pi cancels in the difference)."""
    rng = np.random.default_rng(5)
    n = 14
    x = np.linspace(-1, 1, n)
    V = np.vander(x, 2, increasing=True)
    dip = 1 - 0.3 * np.exp(-0.5 * (x / 0.25) ** 2)
    y = (1.002 + 0.01 * x) * dip + rng.normal(0, 4e-3, n)
    e = np.full(n, 4e-3)
    shifted = 1 - 0.3 * np.exp(-0.5 * ((x - 0.15) / 0.28) ** 2)

    def closed(m):
        return f26._event_loglike(m, y, e, V, None, 1.0, None, None)[0]

    def brute(m):
        c0, c1 = np.meshgrid(np.linspace(0.97, 1.04, 801), np.linspace(-0.06, 0.08, 801), indexing="ij")
        pred = (c0[..., None] + c1[..., None] * x) * m
        ll = -0.5 * np.sum(((y - pred) / e) ** 2, axis=-1) - np.sum(np.log(e * np.sqrt(2 * np.pi)))
        peak = ll.max()
        return peak + np.log(np.sum(np.exp(ll - peak)) * (c0[1, 0] - c0[0, 0]) * (c1[0, 1] - c1[0, 0]))

    assert closed(dip) - closed(shifted) == pytest.approx(brute(dip) - brute(shifted), abs=2e-3)


def test_gp_with_vanishing_amplitude_reduces_to_white_noise():
    groups, ev, p, _ = _groups()
    th = _theta(p, groups, lna=-12.0)
    white, _ = _groups(gp=False)[:2]
    th_w = _theta(p, white)
    assert f26._log_like_events(th, groups, PERIOD, p["t0"]) == pytest.approx(f26._log_like_events(th_w, white, PERIOD, p["t0"]), abs=0.05)


def test_red_noise_amplitude_matters_when_the_data_are_correlated():
    # strongly correlated residuals must be much more probable under a matching GP than under white noise alone
    groups, ev, p, _ = _groups(noise=0.0)
    rng = np.random.default_rng(1)
    for g in groups:
        for evn in g["events"]:
            sl = evn["sl"]
            tt = g["t"][sl]
            a = np.sqrt(3.0) * np.abs(tt[:, None] - tt[None, :]) / 0.3
            C = 4e-3 ** 2 * (1 + a) * np.exp(-a) + 1e-14 * np.eye(len(tt))
            g["y"][sl] = g["y"][sl] + np.linalg.cholesky(C) @ rng.normal(size=len(tt))
        g["e"][:] = 3e-4
    with_gp = f26._log_like_events(_theta(p, groups, lna=np.log(4e-3), lnrho=np.log(0.3)), groups, PERIOD, p["t0"])
    no_gp = f26._log_like_events(_theta(p, groups, lna=-12.0, lnrho=np.log(0.3)), groups, PERIOD, p["t0"])
    assert with_gp > no_gp + 50


def test_template_model_matches_direct_ellc_for_binned_and_long_cadence_points():
    groups, ev, p, _ = _groups(cadence_min=2.0, days=12.0)
    assert groups[0]["w"] > 0                                    # 2-minute data are binned wider than the cadence
    pp = f26.unpack(np.array([0.0, p["rsum"], p["k"], p["cosi"], p["J"], p["fc"], p["fs"], 0.02, 0.4, 0.4, 2e-5]), p["t0"])
    models = f26._event_models(pp, PERIOD + pp["dP"], groups)
    for g, m in zip(groups, models):
        direct = f26.ellc_lc(g["t"], pp, PERIOD + pp["dP"], g["w"], 25, 0.0)
        assert np.sqrt(np.mean((m - direct) ** 2)) < 3e-5
        assert np.max(np.abs(m - direct)) < 1.5e-4
    # long cadence (30 min) is integrated over the exposure, not sampled at the centre
    g30, _, p30, _ = _groups(cadence_min=30.0, noise=1e-4, duration=0.3)
    assert g30[0]["w"] == pytest.approx(30.0 / 1440.0)
    m30 = f26._event_models(f26.unpack(_theta(p30, g30)[:11], p30["t0"]), PERIOD, g30)[0]
    sampled = f26.ellc_lc(g30[0]["t"], f26.unpack(_theta(p30, g30)[:11], p30["t0"]), PERIOD)
    smeared = f26.ellc_lc(g30[0]["t"], f26.unpack(_theta(p30, g30)[:11], p30["t0"]), PERIOD, 30.0 / 1440.0, 25)
    assert np.sqrt(np.mean((m30 - smeared) ** 2)) < 0.25 * np.sqrt(np.mean((sampled - smeared) ** 2))


def test_events_without_a_baseline_on_both_sides_are_dropped_and_scatter_is_measured_outside_eclipse():
    t, f, s, p = _lightcurve(noise=8e-4)
    keep = ~((t > 1501.0 - 0.45) & (t < 1501.0 - 0.13))
    ev = f26.cut_events(t[keep], f[keep], s[keep], PERIOD, p["t0"], 0.25, _sec_phase(p))
    centres = np.array([e["tc"] for e in ev if e["kind"] == "primary"])
    assert not np.any(np.abs(centres - 1501.0) < 0.05)
    assert np.any(np.abs(centres - (1501.0 + PERIOD)) < 0.05)
    assert all(e["ooe"].sum() >= 10 and e["y"].shape == e["t"].shape for e in ev)
    # the scatter is the injected white noise, not the eclipse slope (10-minute data, so the slope per step is large)
    assert f26._sector_sigma(ev) == pytest.approx(8e-4, rel=0.15)


def test_spike_filter_keeps_steep_eclipse_slopes_and_removes_single_spikes():
    # 2-minute data through a deep eclipse: the flux changes by several sigma per step on the slopes
    p = _params(rsum=0.12, cosi=0.0)
    t = 1501.0 + np.arange(-0.5, 0.5, 2.0 / 1440.0)
    y = f26.ellc_lc(t, p, PERIOD) + np.random.default_rng(0).normal(0, 6e-4, t.size)
    assert np.max(np.abs(np.diff(y))) > 5 * 6e-4          # the slopes really are steeper than the noise
    assert f26._spike_free(y).all()                      # nothing real is thrown away
    bad = y.copy()
    bad[100], bad[300] = bad[100] + 0.02, bad[300] - 0.02
    keep = f26._spike_free(bad)
    assert not keep[100] and not keep[300]
    assert keep.sum() >= t.size - 6                       # a spike costs at most its two neighbours as well


def test_every_sector_gets_its_own_white_noise_scale_and_one_bin_width():
    t1, f1, s1, p = _lightcurve(seed=3)
    t2, f2, s2, _ = _lightcurve(seed=4)
    t = np.concatenate([t1, t2 + 60.0])
    f = np.concatenate([f1, f2])
    s = np.concatenate([np.full(t1.size, 7), np.full(t2.size, 8)])
    ev = f26.cut_events(t, f, s, PERIOD, p["t0"], 0.25, _sec_phase(p))
    groups = f26.event_groups(ev, 0.25)
    assert [g["sectors"] for g in groups] == [[7], [8]]
    assert {g["n_white"] for g in groups} == {2}
    assert [g["noise_idx"] for g in groups] == [0, 1]
    assert len({g["w"] for g in groups}) == 1


def test_prior_bounds_for_noise_parameters():
    groups, ev, p, _ = _groups()
    th = _theta(p, groups)
    n_w = groups[0]["n_white"]
    assert np.isfinite(f26.log_prior_events(th, n_w, True))
    for idx, bad in ((len(f26.PARAMS), 3.5), (len(f26.PARAMS) + n_w, 0.0), (len(f26.PARAMS) + n_w + 1, 2.0)):
        t2 = th.copy()
        t2[idx] = bad
        assert f26.log_prior_events(t2, n_w, True) == -np.inf


def test_v2_fit_recovers_an_injected_eccentric_binary_and_reports_its_noise_model():
    t, f, s, p = _lightcurve()
    ecosw = p["fc"] ** 2 - p["fs"] ** 2
    ecosw = 0.12 * np.cos(np.radians(70.0))
    res = f26.fit_star(t, f, s, PERIOD, 1501.0, 0.25, ecosw, 0.5, steps=40, noise="v2")
    assert res["status"] == "OK"
    assert res["noise_model"] == "v2" and "integrated out" in res["model"]["detrending"]
    assert len(res["noise_scale"]) == 1 and res["red_noise"]["events"] > 4
    q = res["params"]
    assert q["ecosw"]["median"] == pytest.approx(ecosw, abs=0.01)
    assert q["incl"]["median"] == pytest.approx(87.5, abs=1.5)
    assert q["e"]["median"] == pytest.approx(0.12, abs=0.06)


def test_a_star_with_many_sectors_shares_white_noise_scales_in_blocks():
    t0_, f0_, s0_, p = _lightcurve(seed=3, days=12.0)
    ts, fs, ss = [], [], []
    for i in range(20):                                      # 20 sectors, each a copy of the same 12 days
        ts.append(t0_ + 399.6 * i)                             # 108 periods: the eclipses stay on the ephemeris
        fs.append(f0_)
        ss.append(np.full(t0_.size, 10 + i))
    t, f, s = np.concatenate(ts), np.concatenate(fs), np.concatenate(ss)
    ev = f26.cut_events(t, f, s, PERIOD, p["t0"], 0.25, _sec_phase(p))
    groups = f26.event_groups(ev, 0.25)
    assert len(groups) == 20
    assert {g["n_white"] for g in groups} == {f26.MAX_NOISE_BLOCKS}
    assert [g["noise_idx"] for g in groups] == sorted(g["noise_idx"] for g in groups)       # consecutive sectors share a block
    assert set(g["noise_idx"] for g in groups) == set(range(f26.MAX_NOISE_BLOCKS))
    th = _theta(p, groups)
    assert len(th) == len(f26.PARAMS) + f26.MAX_NOISE_BLOCKS + 2
    assert np.isfinite(f26.log_prior_events(th, groups[0]["n_white"], True))
