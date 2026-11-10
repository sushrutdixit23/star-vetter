import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f22_eccentricity as f22  # noqa: E402
import f23_etv as f23  # noqa: E402


def synth(P=3.0, t0=0.3, dur=0.12, d1=0.2, d2=0.08, phase2=0.5, n_days=54.0, cad=2 / 1440, noise=0.002, seed=0, t_shift=None):
    rng = np.random.default_rng(seed)
    t = np.arange(0, n_days, cad)
    f = np.ones_like(t)
    ph = ((t - t0) / P) % 1.0
    for c, d in ((0.0, d1), (phase2, d2)):
        x = np.abs(((ph - c + 0.5) % 1.0) - 0.5) * P
        f -= d * np.clip(1 - x / (dur / 2), 0, None) ** 0.5 * (x < dur / 2)
    f += rng.normal(0, noise, t.size)
    sector = (t // 27).astype(int) + 1
    return t, f, sector


def test_circular_orbit_is_not_called_eccentric():
    t, f, s = synth(phase2=0.5)
    r = f22.assess(t, f, 3.0, 0.3, 0.12, s)
    assert r["verdict"] == "CIRCULAR_WITHIN_ERRORS"
    assert abs(r["ecosw"]) < 0.01


def test_displaced_secondary_gives_ecosw():
    t, f, s = synth(phase2=0.6)
    r = f22.assess(t, f, 3.0, 0.3, 0.12, s)
    assert r["verdict"] == "ECCENTRIC"
    assert r["ecosw"] == pytest.approx(0.5 * np.pi * 0.1, abs=0.01)


def test_no_secondary_is_reported_as_such():
    t, f, s = synth(d2=0.0)
    assert f22.assess(t, f, 3.0, 0.3, 0.12, s)["verdict"] == "NO_SECONDARY"


def test_alternation_measures_offset_at_twice_the_period():
    P = 2.0
    pts = [{"epoch": e, "oc_min": (30.0 if e % 2 else -30.0) + np.random.default_rng(e).normal(0, 1), "err_min": 1.0} for e in range(20)]
    a = f23.np and f22.alternation(pts, P)
    assert a["odd_even_time_offset_min"] == pytest.approx(-60.0, abs=3)
    assert a["true_period_days"] == 4.0
    assert a["ecosw"] == pytest.approx(0.5 * np.pi * 60.0 / 1440.0 / 4.0, rel=0.1)
    assert f22.alternation(pts[:4], P) is None


def test_ztf_secondary_check_finds_the_same_phase_and_rejects_a_wrong_one():
    rng = np.random.default_rng(4)
    t = np.sort(rng.uniform(0, 2000, 1500))
    P, t0, dur = 3.0, 0.3, 0.15
    ph = ((t - t0) / P) % 1.0
    f = np.ones_like(t)
    for c, d in ((0.0, 0.3), (0.62, 0.15)):
        x = np.abs(((ph - c + 0.5) % 1.0) - 0.5) * P
        f -= d * (x < dur / 2)
    f += rng.normal(0, 0.01, t.size)
    good = f22.ztf_secondary(t, f, P, t0, dur, 0.62)
    assert good["confirmed"]
    bad = f22.ztf_secondary(t, f, P, t0, dur, 0.40)
    assert not bad["confirmed"]


def test_etv_constant_period_is_constant_and_a_parabola_is_not():
    E = np.arange(0, 1200, 120.0)
    grp = lambda y: [{"source": "TESS" if i < 4 else "ZTF", "epoch": float(e), "oc_min": float(v), "err_min": 2.0} for i, (e, v) in enumerate(zip(E, y))]
    rng = np.random.default_rng(1)
    flat = f23.assess(grp(rng.normal(0, 2.0, E.size)))
    assert flat["verdict"] == "CONSTANT"
    curved = f23.assess(grp(1e-4 * (E - 600) ** 2 + rng.normal(0, 2.0, E.size)))
    assert curved["verdict"] == "DRIFT_CONFIRMED"
    assert curved["p_quad"] > 1e-3          # and the parabola describes it


def test_shared_template_puts_tess_and_ztf_on_one_zero_point():
    P, t0 = 2.0, 2459000.3
    tp = np.linspace(-0.5, 0.5, 201)
    tf = 1 - 0.2 * (np.abs(tp) < 0.02)
    rng = np.random.default_rng(2)
    tt = np.arange(2459000.0, 2459054.0, 2 / 1440)
    ft = np.interp(f22.fold_phase(tt, P, t0), tp, tf, period=1.0) + rng.normal(0, 0.002, tt.size)
    tz = np.sort(rng.uniform(2458300, 2460500, 900))
    fz = np.interp(f22.fold_phase(tz, P, t0), tp, tf, period=1.0) + rng.normal(0, 0.01, tz.size)
    g = f23.tess_sector_times(tt, ft, (tt // 27).astype(int), P, t0, tp, tf, 0.03, n_boot=5)
    g += f23.ztf_season_times(tz, fz, P, t0, tp, tf, 0.03, n_boot=5)
    assert len(g) >= 4
    assert max(abs(x["oc_min"]) for x in g) < 5.0
    assert f23.assess(sorted(g, key=lambda x: x["epoch"]))["verdict"] == "CONSTANT"


def test_fast_pulsator_is_not_called_an_eccentric_binary():
    # a 0.13 d sinusoid folded at 0.79 d makes dips at arbitrary, stable phases
    t, f, s = synth(P=0.79, t0=0.1, dur=0.05, d1=0.0, d2=0.0, noise=0.001, n_days=80.0)
    f = f + 0.02 * np.sin(2 * np.pi * t / 0.131)
    r = f22.assess(t, f, 0.79, 0.1, 0.05, s)
    assert r["verdict"] != "ECCENTRIC"


def test_third_dip_means_period_multiple():
    # dips every quarter of the folded period: the pipeline period is four times the true one
    t, f, s = synth(P=4.0, t0=0.2, dur=0.12, d1=0.1, d2=0.1, phase2=0.25, noise=0.001, n_days=120.0)
    ph = ((t - 0.2) / 4.0) % 1.0
    x = np.abs(((ph - 0.75 + 0.5) % 1.0) - 0.5) * 4.0
    f -= 0.1 * np.clip(1 - x / 0.06, 0, None) ** 0.5 * (x < 0.06)
    r = f22.assess(t, f, 4.0, 0.2, 0.12, s)
    assert r["verdict"] in ("PERIOD_MULTIPLE_SUSPECTED", "NO_SECONDARY", "SECONDARY_NOT_REPRODUCED", "CIRCULAR_WITHIN_ERRORS")


def test_real_eccentric_orbit_survives_the_vetoes():
    t, f, s = synth(phase2=0.6, d2=0.12, noise=0.001)
    r = f22.assess(t, f, 3.0, 0.3, 0.12, s)
    assert r["verdict"] == "ECCENTRIC"
    assert r["fast_signal"] is None or r["fast_signal"]["fap"] > 1e-3 or r["fast_signal"]["amplitude_over_secondary_depth"] < 0.5


def test_period_refinement_uses_only_the_primary():
    rng = np.random.default_rng(2)
    t = np.sort(rng.uniform(0, 1500, 2500))
    P_true, t0, dur = 3.0001, 0.3, 0.15
    ph = ((t - t0) / P_true) % 1.0
    f = np.ones_like(t)
    x = np.abs(((ph + 0.5) % 1.0) - 0.5) * P_true
    f -= 0.3 * (x < dur / 2)
    f += rng.normal(0, 0.01, t.size)
    got = f22.refine_period_primary(t, f, 3.0, t0, dur)
    assert abs(got - P_true) < 1e-4   # drift over 500 cycles stays under a third of the eclipse
