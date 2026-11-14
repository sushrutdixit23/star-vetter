"""Documents a fact about ellc that the v2 likelihood has to cope with (found in the injection diagnosis, data/benchmarks/f34_diagnosis).

When the two stars overlap, ellc does not return NaN: it returns its error sentinel, -DBL_MAX (-1.797e308), which is FINITE.
A guard that only checks np.isfinite therefore lets it through, the cumulative sum in f26._event_models overflows, the event
model becomes NaN, and the Cholesky solve in _event_loglike raises "array must not contain infs or NaNs" -- the ERROR rows
of the registered v2 injection run. f26_ebfit.py is frozen by the registration, so this test only pins the cause; the fix
(reject any model value below 0, and add a detachment condition to the prior) needs a new registration.
"""
import numpy as np
import pytest

import f26_ebfit as f26

ellc = pytest.importorskip("ellc")

OVERLAPPING = {"t0": 0.0, "rsum": 0.375, "k": 0.37, "cosi": 0.25, "J": 0.08, "fc": 0.857, "fs": -0.191, "l3": 0.47,
               "u1": 0.4, "u1b": 0.4, "dP": 0.0}          # e = 0.77: periastron separation 0.23 is below the radius sum 0.375
DETACHED = dict(OVERLAPPING, rsum=0.12, fc=0.1, fs=0.1, l3=0.0, J=0.6, k=0.8, cosi=0.02)


def test_overlap_returns_a_finite_sentinel_not_nan():
    t = np.linspace(0.0, 5.0, 200)
    flux = np.asarray(f26.ellc_lc(t, OVERLAPPING, 5.0), float)
    assert np.all(np.isfinite(flux)), "ellc now returns NaN for overlapping stars: the isfinite guard is enough and this test can go"
    assert np.all(flux < -1e300), "expected ellc's -DBL_MAX sentinel for overlapping stars"


def test_detached_system_is_an_ordinary_light_curve():
    t = np.linspace(0.0, 5.0, 400)
    flux = np.asarray(f26.ellc_lc(t, DETACHED, 5.0), float)
    assert np.all(np.isfinite(flux)) and flux.min() > 0.3 and flux.max() <= 1.0 + 1e-9
