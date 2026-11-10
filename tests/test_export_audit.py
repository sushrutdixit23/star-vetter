import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_audit as ea  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_wilson_known_values():
    lo, hi = ea.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    lo0, hi0 = ea.wilson(0, 10)
    assert lo0 == 0.0 and hi0 == pytest.approx(0.2775, abs=1e-3)
    assert ea.wilson(0, 0) == (0.0, 1.0)
    lo1, hi1 = ea.wilson(10, 10)
    assert hi1 == pytest.approx(1.0, abs=1e-9) and lo1 == pytest.approx(0.7225, abs=1e-3)


def test_strata_cover_every_star_and_edges_belong_to_lower_stratum():
    rng = np.random.default_rng(1)
    pop = rng.uniform(8, 16, 5000)
    edges = ea.strata_edges(pop)
    assert len(edges) == ea.N_STRATA - 1 and edges == sorted(edges)
    idx = ea.assign_stratum(pop, edges)
    counts = np.bincount(idx, minlength=ea.N_STRATA)
    assert counts.sum() == len(pop) and counts.min() > 900   # quintiles, roughly equal
    assert ea.assign_stratum([edges[0]], edges)[0] == 0
    assert ea.assign_stratum([-5.0, 99.0], edges).tolist() == [0, ea.N_STRATA - 1]


def _synthetic():
    # 10 stars, 5 in each of two brightness halves; population is 10x larger
    rows = []
    for i in range(10):
        rows.append({"TIC": 100 + i, "Tmag": 10.0 if i < 5 else 14.0, "status": "OK" if i != 9 else "NO_DATA"})
    manifest = pd.DataFrame(rows)
    vetting = pd.DataFrame({"TIC": [100 + i for i in range(9)] + [999], "status": ["OK"] * 8 + ["UNRELIABLE_DATA", "OK"]})
    novelty = pd.DataFrame({
        "TIC": [100, 101, 105, 999],            # 999 is outside the frame
        "verdict": ["NOVEL", "KNOWN_OTHER_TYPE", "NOVEL", "NOVEL"],
        "bls_period": [0.5, 3.0, 12.0, 4.0],
    })
    pixel = pd.DataFrame({
        "TIC": [100, 105, 999, 427332229],
        "role": ["candidate", "candidate", "candidate", "control"],
        "verdict": ["ON_TARGET", "OFF_TARGET", "ON_TARGET", "ON_TARGET"],
    })
    pop = np.array([10.0] * 50 + [14.0] * 50)
    bench = {"funnel": [{"label": "Light curve fetched", "count": 40}], "recall": {"recovered": 10, "sampled": 50},
             "by_tmag": [{"bin": "<12", "recovered": 1, "n": 4}]}
    return manifest, vetting, novelty, pixel, pop, bench


def test_funnel_is_nested_and_ignores_stars_outside_the_frame():
    a = ea.build_audit(*_synthetic())
    f = {x["key"]: x["count"] for x in a["funnel"]}
    assert f["sampled"] == 10 and f["usable"] == 9
    assert f["passed"] == 3                      # 100, 101, 105; 999 excluded
    assert f["novel"] == 2 and f["on_target"] == 1 and f["pixel_checked"] == 2
    assert f["on_target"] <= f["pixel_checked"] <= f["novel"] <= f["passed"] <= f["usable"] <= f["sampled"]
    assert any("1 star(s) in the novelty file are not in the sampling frame" in n for n in a["notes"])
    # the control star is never counted
    assert sum(r["on_target"] for r in a["strata"]) == 1


def test_strata_rows_sum_to_the_funnel_and_weights_sum_to_one():
    a = ea.build_audit(*_synthetic())
    assert sum(r["sampled"] for r in a["strata"]) == 10
    assert sum(r["population"] for r in a["strata"]) == 100
    assert sum(r["weight"] for r in a["strata"]) == pytest.approx(1.0)
    for r in a["strata"]:
        iv = r["on_target_per_usable"]
        assert iv["lo"] <= (iv["rate"] or 0.0) <= iv["hi"]


def test_population_rate_is_reweighted_not_pooled():
    # one stratum is 90% of the list but only 10% of the sample: the pooled
    # sample rate is 0.5*0.1+... ; the weighted rate must follow the list.
    n_h = [100, 100]
    k_h = [50, 0]          # stratum 0 rate .5, stratum 1 rate 0
    w = [0.1, 0.9]
    rng = np.random.default_rng(0)
    d = ea.posterior_draws(k_h, n_h, w, rng, draws=20000)
    s = ea.summarize(d)
    assert s["median"] == pytest.approx(0.05, abs=0.01)     # 0.1*0.5, not the pooled 0.25
    assert s["lo"] < s["median"] < s["hi"]


def test_output_is_reproducible_and_correction_is_flagged_provisional():
    from datetime import datetime, timezone
    now = datetime(2026, 11, 8, tzinfo=timezone.utc)
    a = ea.build_audit(*_synthetic(), now=now)
    b = ea.build_audit(*_synthetic(), now=now)
    assert a == b
    pc = a["provisional_correction"]
    assert "Provisional" in pc["label"] and "LOWER bound" in pc["assumption"]
    assert 0.0 <= pc["value"]["lo"] <= pc["value"]["median"] <= pc["value"]["hi"] <= 1.0


def test_injection_recall_gives_a_second_corrected_rate_and_a_consistency_flag():
    base = ea.build_audit(*_synthetic())
    assert "with_injection_recall" not in base["provisional_correction"]
    inj = ea.build_audit(*_synthetic(), injection={"k": 87, "n": 306})
    w = inj["provisional_correction"]["with_injection_recall"]
    assert inj["provisional_correction"]["value"] == base["provisional_correction"]["value"]   # first estimate unchanged
    assert w["recall"]["k"] == 87 and 0.0 <= w["value"]["lo"] <= w["value"]["hi"] <= 1.0
    # a much higher recall means a smaller correction
    hi = ea.build_audit(*_synthetic(), injection={"k": 300, "n": 306})["provisional_correction"]["with_injection_recall"]
    assert hi["value"]["median"] <= w["value"]["median"]


def test_period_table_counts_match_passed():
    a = ea.build_audit(*_synthetic())
    assert sum(p["passed"] for p in a["periods"]) == 3
    by = {p["bin"]: p for p in a["periods"]}
    assert by["<1 d"]["passed"] == 1 and by["<1 d"]["on_target"] == 1
    assert by["10-20 d"]["passed"] == 1 and by["10-20 d"]["on_target"] == 0


def test_published_audit_matches_the_pipeline_files():
    p = ROOT / "site/public/data/audit.json"
    if not p.exists():
        pytest.skip("audit.json not generated")
    a = json.loads(p.read_text(encoding="utf-8"))
    f = {x["key"]: x["count"] for x in a["funnel"]}
    stats = json.loads((ROOT / "site/public/data/pipeline_stats.json").read_text(encoding="utf-8"))
    by_label = {x["label"]: x["count"] for x in stats["funnel"]}
    assert f["sampled"] == by_label["Targets sampled and fetch attempted"]
    assert f["usable"] == by_label["Usable light curve obtained"]
    assert f["on_target"] == by_label["Confirmed on-target"]
    # every candidate on the site is in this audit's on-target count
    tics = {q.stem[3:] for q in (ROOT / "site/public/data/detail").glob("TIC*.json")}
    assert len(tics) == f["on_target"] or len(tics) <= f["on_target"]
    assert a["frame"]["population"] > 800000
    assert p.read_bytes().isascii()


def test_quiet_host_recall_adds_a_third_corrected_rate():
    q = ea.build_audit(*_synthetic(), injection={"k": 87, "n": 306}, injection_quiet={"k": 153, "n": 293})
    pc = q["provisional_correction"]
    assert pc["with_quiet_host_recall"]["recall"]["k"] == 153
    assert pc["with_quiet_host_recall"]["value"]["median"] <= pc["with_injection_recall"]["value"]["median"]
    assert "with_quiet_host_recall" not in ea.build_audit(*_synthetic(), injection={"k": 87, "n": 306})["provisional_correction"]
