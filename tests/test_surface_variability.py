import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_surface_variability as ev  # noqa: E402

P, T0, DUR = 3.0, 10.0, 0.12


def make_sector(start=0.0, span=26.0, cad_min=2.0, seed=0, noise=0.002, rot=None, rot_amp=0.0, flares=(), harmonics=(0, 0, 0, 0)):
    rng = np.random.default_rng(seed)
    t = np.arange(start, start + span, cad_min / 1440.0)
    gap = (t > start + span / 2 - 0.5) & (t < start + span / 2 + 0.5)
    t = t[~gap]
    ph = ((t - T0) / P) % 1.0
    f = np.ones_like(t)
    f -= 0.2 * (np.abs((ph + 0.5) % 1 - 0.5) < DUR / P / 2)
    f -= 0.08 * (np.abs(((ph - 0.5) + 0.5) % 1 - 0.5) < DUR / P / 2)
    a1, b1, a2, b2 = harmonics
    phi = 2 * math.pi * ph
    f += a1 * np.cos(phi) + b1 * np.sin(phi) + a2 * np.cos(2 * phi) + b2 * np.sin(2 * phi)
    if rot:
        f += rot_amp * np.sin(2 * math.pi * t / rot + 1.0)
    f += rng.normal(0, noise, len(t))
    for tf, amp in flares:
        d = t - tf
        f += np.where(d >= 0, amp * np.exp(-d / 0.01), 0.0) * (d < 0.1)
    return t, f


def stack(sectors):
    t = np.concatenate([s[0] for s in sectors])
    f = np.concatenate([s[1] for s in sectors])
    sec = np.concatenate([np.full(len(s[0]), i + 1) for i, s in enumerate(sectors)])
    return t, f, sec


def test_align_sector_finds_shifted_eclipse():
    t, f = make_sector(seed=1)
    got = ev.align_sector(t, f, P, T0 + 0.4, DUR)
    assert got is not None and abs(((got - T0) / P + 0.5) % 1 - 0.5) * P < 0.05


def test_rotation_signal_in_two_segments_is_detected():
    t, f, sec = stack([make_sector(seed=2, rot=1.7, rot_amp=0.01), make_sector(start=30.0, seed=3, rot=1.7, rot_amp=0.01)])
    r = ev.analyse_star(t, f, sec, P, T0, DUR)
    assert r["spots_A"]["status"] == "detected"
    assert abs(r["spots_A"]["period_days"] - 1.7) < 0.1


def test_orbital_harmonic_period_is_not_called_a_spot():
    t, f, sec = stack([make_sector(seed=4, rot=P / 2, rot_amp=0.01), make_sector(start=30.0, seed=5, rot=P / 2, rot_amp=0.01)])
    r = ev.analyse_star(t, f, sec, P, T0, DUR)
    assert r["spots_A"]["status"] != "detected"


def test_null_stars_are_not_flagged():
    bad = 0
    for s in range(12):
        t, f, sec = stack([make_sector(seed=100 + s), make_sector(start=30.0, seed=200 + s)])
        r = ev.analyse_star(t, f, sec, P, T0, DUR)
        bad += r["spots_A"]["status"] == "detected" or r["spots_B"]["status"] == "detected" or r["flares"]["status"] == "detected"
    assert bad == 0


def test_stable_tide_does_not_look_like_changing_modulation():
    t, f, sec = stack([make_sector(seed=6, harmonics=(0, 0, -0.01, 0)), make_sector(start=30.0, seed=7, harmonics=(0, 0, -0.01, 0))])
    assert ev.analyse_star(t, f, sec, P, T0, DUR)["spots_B"]["status"] != "detected"


def test_changing_modulation_is_detected():
    t, f, sec = stack([make_sector(seed=8, harmonics=(0, 0, 0, 0)), make_sector(start=30.0, seed=9, harmonics=(0.02, 0, 0, 0))])
    assert ev.analyse_star(t, f, sec, P, T0, DUR)["spots_B"]["status"] == "detected"


def test_injected_flares_are_found_and_false_alarms_are_few():
    fl = [(5.0, 0.05), (9.3, 0.04), (14.2, 0.06), (19.1, 0.05)]
    t, f = make_sector(seed=10, flares=fl)
    mask = ev.eclipse_mask(t, P, T0, DUR)
    out = ev.flare_summary(t, f, mask, 2.0)
    assert out["status"] == "detected"
    assert out["n_candidates"] >= 3 and out["n_false_alarms"] <= 1
    assert out["biggest"]["amp"] > 0.03


def test_flares_not_tested_at_slow_cadence():
    t, f = make_sector(seed=11, cad_min=10.0)
    assert ev.flare_summary(t, f, ev.eclipse_mask(t, P, T0, DUR), 10.0)["status"] == "not_tested"


def test_flares_inside_eclipses_are_ignored():
    t, f = make_sector(seed=12, flares=[(T0 + 3 * P, 0.1), (T0 + 5 * P, 0.1), (T0 + 7 * P, 0.1)])
    out = ev.flare_summary(t, f, ev.eclipse_mask(t, P, T0, DUR), 2.0)
    assert out["status"] != "detected"


def test_single_segment_is_not_tested():
    t, f, sec = stack([make_sector(seed=13, span=12.0)])
    r = ev.analyse_star(t, f, sec, P, T0, DUR)
    assert r["spots_A"]["status"] == "not_tested" and r["spots_B"]["status"] == "not_tested"
