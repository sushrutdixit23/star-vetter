import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_surface_evidence as ese  # noqa: E402


def synth(a_ell=0.0, a_ref=0.0, b_ell=0.0, noise=0.01, n=2500, seed=0, dur_frac=0.05, sec=0.5, eclipse=True):
    rng = np.random.default_rng(seed)
    ph = rng.uniform(-0.5, 0.5, n)
    phi = 2 * math.pi * ph
    f = 1.0 - a_ell * np.cos(2 * phi) + b_ell * np.sin(2 * phi) - a_ref * np.cos(phi)
    if eclipse:
        for c, depth in ((0.0, 0.2), (sec, 0.08)):
            d = np.abs((ph - c + 0.5) % 1.0 - 0.5)
            f = f - depth * (d < dur_frac / 2)
    return ph, f + rng.normal(0, noise, n)


def test_recovers_ellipsoidal_and_ignores_eclipses():
    ph, f = synth(a_ell=0.02)
    m = ese.measure(ph, f, 0.05, 0.5)
    assert abs(m["a_ell"] - 0.02) < 0.003
    tides, heating, el = ese.judge(m)
    assert tides and not heating
    assert 0 < el < 0.05


def test_recovers_reflection_only():
    ph, f = synth(a_ref=0.03)
    tides, heating, el = ese.judge(ese.measure(ph, f, 0.05, 0.5))
    assert heating and not tides and el == 0.0


def test_pure_noise_never_triggers():
    hits = 0
    for s in range(300):
        ph, f = synth(seed=s)
        t, h, _ = ese.judge(ese.measure(ph, f, 0.05, 0.5))
        hits += t or h
    assert hits == 0


def test_wrong_sign_is_not_a_tide():
    ph, f = synth(a_ell=-0.03)  # brightest at conjunctions: not an ellipsoidal tide
    assert ese.judge(ese.measure(ph, f, 0.05, 0.5))[0] is False


def test_quadrature_signal_is_rejected():
    ph, f = synth(a_ell=0.01, b_ell=0.03)  # not locked to the eclipses
    assert ese.judge(ese.measure(ph, f, 0.05, 0.5))[0] is False


def test_sinusoidal_or_unusable_curve_gives_nothing():
    ph, f = synth(a_ell=0.03)
    m = ese.measure(ph, f, 0.05, 0.5)
    assert ese.judge(m, sinusoidal=True) == (False, False, 0.0)
    assert ese.judge(None) == (False, False, 0.0)
    assert ese.measure(ph, f, 1.0, 0.5) is None  # eclipses cover everything


def test_outlier_flares_do_not_fake_a_signal():
    ph, f = synth(seed=3)
    f = f.copy()
    f[np.abs(ph) < 0.15] += 0.0
    idx = np.where((ph > 0.2) & (ph < 0.3))[0][:8]
    f[idx] += 0.5
    t, h, _ = ese.judge(ese.measure(ph, f, 0.05, 0.5))
    assert not t and not h
