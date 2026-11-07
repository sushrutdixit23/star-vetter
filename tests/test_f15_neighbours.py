import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f15_neighbours as nb  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_aperture_fraction_is_monotone_and_bounded():
    s = np.array([0.0, 5.0, 20.0, 40.0, 80.0, 200.0])
    f = nb.aperture_fraction(s)
    assert np.all(np.diff(f) < 0) and f[0] == pytest.approx(1 - np.exp(-0.5 * (nb.APERTURE_RADIUS_ARCSEC / nb.PSF_SIGMA_ARCSEC) ** 2)) and f[-1] < 1e-3 and np.all((f >= 0) & (f <= 1))


def test_required_depth_matches_the_hand_formula():
    # same brightness, on top of the target: needs about the observed depth
    assert nb.required_depth(0.02, 12.0, 12.0, 0.0) == pytest.approx(0.02 / nb.aperture_fraction(0.0), rel=1e-9)
    # 5 magnitudes fainter = 100x less light, so a 100x deeper eclipse (before the aperture fraction)
    d = nb.required_depth(0.01, 12.0, 17.0, 0.0)
    assert d == pytest.approx(0.01 * 100.0 / nb.aperture_fraction(0.0), rel=1e-6)
    # brighter neighbour needs less
    assert nb.required_depth(0.01, 12.0, 10.0, 10.0) < 0.01


def test_far_neighbour_needs_more_depth_than_a_near_one():
    near = nb.required_depth(0.01, 12.0, 13.0, 5.0)
    far = nb.required_depth(0.01, 12.0, 13.0, 55.0)
    assert far > 5 * near


def test_centroid_tolerance_floor_and_snr():
    assert nb.centroid_tolerance(1000.0, 6.0) == 6.0                 # floor dominates
    assert nb.centroid_tolerance(2.0, 6.0) == pytest.approx(3 * nb.PSF_SIGMA_ARCSEC / 2.0)
    assert nb.centroid_tolerance(None, 3.0) == pytest.approx(3 * nb.PSF_SIGMA_ARCSEC)


def _nbrs(rows):
    return pd.DataFrame(rows, columns=["nbr_TIC", "nbr_Tmag", "sep_arcsec"])


def test_assess_star_requires_both_brightness_and_centroid_consistency():
    # target Tmag 12, depth 2%, measured offset 3 arcsec
    n = _nbrs([
        (1, 12.5, 4.0),     # bright enough, offset-consistent, close: viable and unseparable
        (2, 12.5, 40.0),    # bright enough but 40" away: centroid says no
        (3, 20.0, 3.0),     # at the right place but ~1500x fainter: cannot give 2%
    ])
    r = nb.assess_star(0.02, 12.0, 3.0, 100.0, n, floor=6.0)
    assert r["bright_enough"] == 2 and r["viable"] == 1 and r["closest_viable"]["tic"] == 1
    assert nb.classify(r) == "UNSEPARABLE_NEIGHBOUR"


def test_assess_star_no_neighbours_and_far_viable():
    assert nb.classify(nb.assess_star(0.02, 12.0, 3.0, 100.0, _nbrs([]), 6.0)) == "NO_VIABLE_NEIGHBOUR"
    n = _nbrs([(9, 11.0, 30.0)])                                       # bright, but the offset says 30"
    r = nb.assess_star(0.02, 12.0, 30.0, 100.0, n, 6.0)
    assert nb.classify(r) == "VIABLE_NEIGHBOUR_AT_OFFSET"


def test_a_larger_floor_never_reduces_viable_neighbours():
    rng = np.random.default_rng(0)
    n = _nbrs([(i, 12.0 + rng.uniform(-1, 3), rng.uniform(1, 60)) for i in range(80)])
    v = [nb.assess_star(0.02, 12.0, 8.0, 50.0, n, f)["viable"] for f in nb.CENTROID_FLOORS_ARCSEC]
    assert v == sorted(v)


def test_build_skips_artifacts_and_the_target_itself():
    blend = pd.DataFrame({"TIC": [1], "bls_depth": [0.02], "target_Tmag": [12.0]})
    pixel = pd.DataFrame({"TIC": [1], "role": ["candidate"], "centroid_offset_arcsec": [3.0], "diff_peak_snr": [80.0]})
    nbrs = pd.DataFrame({
        "target_TIC": [1, 1, 1, 1], "nbr_TIC": [1, 2, 3, 4], "nbr_Tmag": [12.0, 12.5, 12.5, 12.5],
        "sep_arcsec": [0.0, 4.0, 4.0, 40.0], "nbr_disposition": [None, None, "ARTIFACT", None]})
    out = nb.build(blend, nbrs, pixel, {1})
    s = out["stars"]["1"]
    assert s["n_neighbours"] == 2                       # target and the ARTIFACT are dropped
    assert s["status"] == "UNSEPARABLE_NEIGHBOUR" and s["closest_viable"]["tic"] == 2
    assert set(out["summary_by_floor"]) == {"3", "6", "10"}


def test_published_file_covers_every_candidate_and_stays_ascii():
    p = ROOT / "site/public/data/neighbours.json"
    if not p.exists():
        pytest.skip("neighbours.json not generated")
    d = json.loads(p.read_text(encoding="utf-8"))
    dash = json.loads((ROOT / "site/public/data/dashboard.json").read_text(encoding="utf-8"))
    assert set(d["stars"]) == {str(int(s["tic"])) for s in dash["sky"]}
    for fl, c in d["summary_by_floor"].items():
        assert sum(c.values()) == d["stars_assessed"]
    assert p.read_bytes().isascii()
