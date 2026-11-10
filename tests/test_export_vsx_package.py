import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_vsx_package as ev  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def star(tier="INDEPENDENTLY_SUPPORTED", z="CONFIRMED", nov="NO_PRIOR_FOUND", caveats=()):
    return {"evidence_tier": tier, "ztf_status": z, "novelty": nov, "caveats": list(caveats)}


def test_wave_assignment_is_strict():
    assert ev.wave_of(star()) == "wave1"
    assert ev.wave_of(star(caveats=["Gaia RUWE above 1.4"])) == "wave2"
    assert ev.wave_of(star(nov="KNOWN_VARIABLE")) == "existing"
    assert ev.wave_of(star(nov="KNOWN_ECLIPSING")) is None
    assert ev.wave_of(star(nov="KNOWN_BINARY")) is None
    assert ev.wave_of(star(tier="TESS_ONLY_CLEAN")) is None      # TESS-only is never submitted
    assert ev.wave_of(star(tier="DISFAVOURED")) is None
    assert ev.wave_of(star(z="INCONCLUSIVE")) is None            # a Gaia-only line is not photometry VSX accepts


def test_amplitude_and_period_choice():
    assert ev.amplitude_mag(0.0888) == pytest.approx(0.1009, abs=1e-3)
    assert ev.amplitude_mag(0.0) is None and ev.amplitude_mag(1.2) is None and ev.amplitude_mag(None) is None
    assert ev.best_period(5.0, 5.0004)[0] == 5.0004                      # agrees within 0.2%
    assert ev.best_period(5.0, 10.0)[0] == 5.0                           # a double period is not silently adopted
    assert ev.best_period(5.0, None)[0] == 5.0


@pytest.mark.skipif(not (ROOT / "site/public/data/evidence.json").exists(), reason="evidence data not generated")
def test_real_package_has_no_wave1_caveats_and_no_tess_only_rows():
    df = ev.build(ROOT)
    w1 = df[df["wave"] == "wave1"]
    assert len(w1) > 0
    assert (w1["caveats"] == "").all()
    assert w1["evidence"].str.contains("ZTF").all()
    assert df["tic"].is_unique
    assert set(df["wave"]) <= {"wave1", "wave2", "existing"}
