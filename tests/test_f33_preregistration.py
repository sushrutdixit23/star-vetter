"""The registration of noise model v2 (data/benchmarks/f33_preregistration.json) must match the code it was written for,
and the v1 numbers it quotes must be the ones in the data. If f26_ebfit.py has to change after registration, the
registration is superseded by a new file, not edited."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PRE = json.loads((ROOT / "data" / "benchmarks" / "f33_preregistration.json").read_text(encoding="utf-8"))


def test_registration_names_a_commit_and_a_code_hash():
    assert "PLACEHOLDER" not in PRE["code_frozen_at"]
    assert len(PRE["f26_ebfit_sha256"]) == 64


def test_f26_ebfit_is_the_registered_code():
    # line endings are normalised so a Windows checkout with CRLF gives the same hash
    raw = (ROOT / "f26_ebfit.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == PRE["f26_ebfit_sha256"], "f26_ebfit.py changed after the v2 registration"


def test_frozen_constants_match_the_code():
    pytest.importorskip("ellc")
    import f26_ebfit as f26
    c = PRE["frozen_constants"]
    assert f26.EVENT_MAX_POINTS == c["EVENT_MAX_POINTS"] and f26.EVENT_WINDOW == c["EVENT_WINDOW"]
    assert f26.MAX_NOISE_BLOCKS == c["MAX_NOISE_BLOCKS"]
    assert f26.TEMPLATE_STEP_DAYS == pytest.approx(c["TEMPLATE_STEP_DAYS"])
    assert list(f26.GP_LNA_BOUNDS) == c["GP_LNA_BOUNDS"] and f26.CLIP_MAD == c["CLIP_MAD"]
    assert np.exp(f26.GP_LNRHO_BOUNDS) == pytest.approx(c["GP_LNRHO_BOUNDS_DAYS"])
    assert "diff_step\": 1e-4" in (ROOT / "f26_ebfit.py").read_text(encoding="utf-8")


def test_quoted_v1_baseline_is_what_the_data_say():
    inj = json.loads((ROOT / "data" / "processed" / "f30_injection.json").read_text(encoding="utf-8"))
    b = PRE["v1_baseline"]
    for q, v in b["coverage_68"].items():
        assert inj["overall"]["by_quantity"][q]["coverage_68"] == pytest.approx(v, abs=0.006)
    assert inj["overall"]["n_fitted"] == b["injections_fitted"]
    assert sum(1 for r in inj["rows"] if r.get("converged")) == b["injections_converged"]
    bench = json.loads((ROOT / "data" / "processed" / "f29_benchmarks.json").read_text(encoding="utf-8"))["summary"]
    assert bench["passed"] == b["benchmark_runs_passed"] and bench["runs"] == b["benchmark_runs"]
    assert bench["systems_passing_both_cadences"] == b["benchmark_systems_passing_both_cadences"]


def test_the_binomial_band_is_the_one_stated():
    n, p = 48, 0.68
    half = 1.96 * np.sqrt(p * (1 - p) / n)
    assert (p - half, p + half) == pytest.approx((0.55, 0.81), abs=0.005)


def test_v2_workflow_runs_the_registered_design_and_touches_no_site_file():
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "physics-v2.yml").read_text(encoding="utf-8"))
    text = (ROOT / ".github" / "workflows" / "physics-v2.yml").read_text(encoding="utf-8")
    jobs = wf["jobs"]
    assert set(jobs) == {"benchmark", "injection", "merge"}
    assert sorted(jobs["injection"]["strategy"]["matrix"]["seed"]) == [29, 33]
    assert jobs["injection"]["strategy"]["matrix"]["start"] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert sorted(jobs["injection"]["strategy"]["matrix"]["host"]) == [43785616, 318887646, 370553309]
    assert text.count("--noise v2") == 2
    assert wf["permissions"] == {"contents": "read"}            # nothing is committed by the workflow
    assert "git push" not in text and "site/" not in text
