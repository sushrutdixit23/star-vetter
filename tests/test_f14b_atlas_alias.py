import json
import sys
from math import comb
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f14b_atlas_alias as aa  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_hypothesis_space_size_and_order():
    h = aa.hypotheses()
    assert len(h) == len(set(h)) == 8 * (1 + 4 * 2)          # j=0 once, four j values x two signs
    assert h[0][1] == 0.0 and h[0][0] == 1.0                  # the identity comes first
    first_sidereal = next(i for i, x in enumerate(h) if x[1] != 0.0)
    assert all(x[1] == 0.0 for x in h[:first_sidereal])      # pure harmonics before any alias


def test_pure_harmonics_are_found_and_labelled():
    ex = aa.explain(1.0, 3.0)                                 # ATLAS reported 3x the TESS period
    assert ex["kind"] == "harmonic" and ex["multiplier"] == pytest.approx(1.0 / 3.0)
    assert aa.explain(2.0, 2.0)["multiplier"] == 1.0
    assert aa.explain(1.0, 0.5)["multiplier"] == 2.0


def test_sidereal_alias_is_found():
    p_atlas = 2.0
    nu = 1.0 / p_atlas + 1.0 / aa.SIDEREAL_DAY                # f=1, j=1, s=+1
    ex = aa.explain(1.0 / nu, p_atlas)
    # several hypotheses can land within the tolerance (the space is crowded), so
    # check that the one returned is a sidereal alias that reproduces the frequency
    assert ex["kind"] == "sidereal"
    pred = aa.predicted_frequency(p_atlas, ex["multiplier"], ex["sidereal_order"], ex["sign"])
    assert abs(pred - nu) <= aa.TOL_FREQ


def test_tolerance_is_the_atlas_frequency_resolution():
    p_atlas = 4.0
    nu = 1.0 / p_atlas
    inside = 1.0 / (nu + 0.9 * aa.TOL_FREQ)
    outside = 1.0 / (nu + 3.0 * aa.TOL_FREQ)
    assert aa.explain(inside, p_atlas)["multiplier"] == 1.0
    ex = aa.explain(outside, p_atlas)
    assert ex is None or ex["multiplier"] != 1.0


def test_bad_inputs_return_none():
    assert aa.explain(None, 1.0) is None and aa.explain(1.0, 0) is None and aa.explain(-1.0, 1.0) is None


def test_unrelated_period_is_not_explained():
    assert aa.explain(5.4321, 7.7777) is None


def test_binom_tail_matches_direct_sum():
    assert aa.binom_tail(0, 10, 0.3) == 1.0
    assert aa.binom_tail(3, 10, 0.3) == pytest.approx(sum(comb(10, i) * 0.3 ** i * 0.7 ** (10 - i) for i in range(3, 11)))
    assert aa.binom_tail(10, 10, 0.5) == pytest.approx(0.5 ** 10)


def test_chance_rate_never_pairs_a_star_with_itself():
    # a star's own period would be explained trivially; it must not count
    hit, tot = aa.chance_rate([2.0], {1: 2.0}, [1])
    assert (hit, tot) == (0, 0)
    hit, tot = aa.chance_rate([2.0], {1: 2.0, 2: 2.0, 3: 9.1234}, [1])
    assert tot == 2 and hit == 1


def test_build_uses_only_other_period_rows():
    extra = pd.DataFrame([
        {"tic": 1, "catalog": "atlas", "status": "SAME_STAR_OTHER_PERIOD", "nearest_class": "dubious", "nearest_period_d": 3.0},
        {"tic": 2, "catalog": "atlas", "status": "SAME_STAR_OTHER_PERIOD", "nearest_class": "dubious", "nearest_period_d": 7.77},
        {"tic": 3, "catalog": "atlas", "status": "SAME_STAR_PERIOD_MATCH", "nearest_class": "IRR", "nearest_period_d": 1.5},
        {"tic": 4, "catalog": "atlas", "status": "NO_MATCH", "nearest_class": None, "nearest_period_d": None},
        {"tic": 1, "catalog": "ztf", "status": "SAME_STAR_OTHER_PERIOD", "nearest_class": "EA", "nearest_period_d": 9.0},
    ])
    out = aa.build(extra, {1: 1.0, 2: 5.4321, 3: 1.5, 4: 2.2})
    assert out["tested"] == 2 and out["already_matching_ratio_1_half_2"] == 1
    by = {s["tic"]: s for s in out["stars"]}
    assert by[1]["explained"] and by[1]["explanation"]["kind"] == "harmonic"
    assert not by[2]["explained"]
    assert out["explained"]["k"] == 1 and out["explained"]["n"] == 2
    assert 0.0 <= out["chance"]["pair_rate"] <= 1.0
    assert 0.0 < out["chance"]["p_value_at_least_observed"] <= 1.0


def test_published_file_is_consistent_with_the_extra_catalog_table():
    p = ROOT / "site/public/data/atlas_alias.json"
    if not p.exists():
        pytest.skip("atlas_alias.json not generated")
    d = json.loads(p.read_text(encoding="utf-8"))
    extra = pd.read_csv(ROOT / "data/processed/f14_extra_catalogs.csv")
    n = int(((extra["catalog"].str.lower() == "atlas") & (extra["status"] == "SAME_STAR_OTHER_PERIOD")).sum())
    assert d["tested"] == n == len(d["stars"])
    assert d["explained"]["k"] == sum(s["explained"] for s in d["stars"]) <= d["tested"]
    assert d["explained"]["harmonic_only"] + d["explained"]["with_sidereal"] == d["explained"]["k"]
    assert p.read_bytes().isascii()
