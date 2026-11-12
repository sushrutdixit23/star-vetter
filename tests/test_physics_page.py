import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import export_physics as ep  # noqa: E402

CASES = [(0.0, 0.0, 0.0, 90.0), (0.13, 0.27, 40.0, 87.0), (0.61, 0.46, 250.0, 84.5), (0.9, 0.05, 123.0, 73.4), (-0.2, 0.7, 300.0, 89.0)]


def test_secondary_phase_matches_the_textbook_approximation():
    for e, w in ((0.02, 30.0), (0.05, 200.0), (0.1, 330.0)):
        approx = 0.5 + 2 * e * np.cos(np.radians(w)) / np.pi
        assert ep.secondary_phase_kepler(e, np.radians(w)) == pytest.approx(approx, abs=0.004)
    assert ep.secondary_phase_kepler(0.0, 1.0) == pytest.approx(0.5, abs=1e-12)


def test_primary_eclipse_has_star_two_in_front_at_phase_zero():
    for e, w in ((0.0, 0.0), (0.3, 1.1), (0.6, 4.0)):
        x, y, z = ep.sky_position(0.0, e, w, 88.0)
        assert z > 0 and abs(x) < 0.05 * max(1.0, 1 + e)


def test_typescript_geometry_matches_python():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")
    if (int(ver[0]), int(ver[1])) < (22, 6):
        pytest.skip("node too old for type stripping")
    script = (
        "import {skyPosition, secondaryPhase} from %r;"
        "const cases = %s;"
        "console.log(JSON.stringify(cases.map(([ph,e,w,i]) => {const p = skyPosition(ph,e,w*Math.PI/180,i);"
        "return [p.x,p.y,p.z,secondaryPhase(e,w*Math.PI/180)];})));"
    ) % ((ROOT / "site" / "src" / "lib" / "orbit.ts").as_posix(), json.dumps([list(c) for c in CASES]))
    out = subprocess.run([node, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    for (ph, e, w, i), (x, y, z, sec) in zip(CASES, got):
        px, py, pz = ep.sky_position(ph, e, np.radians(w), i)
        assert (x, y, z) == pytest.approx((px, py, pz), abs=1e-9)
        assert sec == pytest.approx(ep.secondary_phase_kepler(e, np.radians(w)), abs=1e-9)


@pytest.mark.parametrize("e,w_deg,incl", [(0.25, 40.0, 87.0), (0.15, 250.0, 86.0), (0.4, 130.0, 88.5)])
def test_geometry_puts_the_eclipses_where_ellc_puts_them(e, w_deg, incl):
    pytest.importorskip("ellc")
    import f26_ebfit as f26
    r1, r2 = 0.05, 0.04
    w = np.radians(w_deg)
    ph = np.arange(-0.25, 0.75, 0.0005)
    p = {"rsum": r1 + r2, "k": r2 / r1, "cosi": np.cos(np.radians(incl)), "J": 0.9, "fc": np.sqrt(e) * np.cos(w),
         "fs": np.sqrt(e) * np.sin(w), "l3": 0.0, "u1": 0.4, "u1b": 0.4, "t0": 0.0, "dP": 0.0}
    flux = f26.ellc_lc(ph * 10.0, p, 10.0)
    x, y, z = ep.sky_position(ph, e, w, incl)
    overlap = np.hypot(x, y) < r1 + r2
    dark = flux < 1 - 1e-7
    assert np.mean(overlap == dark) > 0.995                       # same phases in eclipse, up to edge pixels
    for centre in (0.0, ep.secondary_phase_kepler(e, w)):
        c = centre if centre < 0.75 else centre - 1.0
        win = np.abs(ph - c) < 0.1
        assert abs(ph[win][np.argmin(flux[win])] - ph[win][np.argmin(np.hypot(x, y)[win])]) < 0.002
