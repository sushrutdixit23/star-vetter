import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f1b_sample as f1b  # noqa: E402


def table(n=5000, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"TIC": np.arange(1, n + 1), "Tmag": rng.uniform(8, 16, n)})


def test_parse_shard():
    assert f1b.parse_shard(None) is None
    assert f1b.parse_shard("") is None
    assert f1b.parse_shard("2/8") == (2, 8)
    for bad in ("8/8", "-1/4", "1/0"):
        with pytest.raises(ValueError):
            f1b.parse_shard(bad)


def test_shards_are_disjoint_and_cover_the_whole_draw():
    df, k, per = table(), 6, 40
    full = f1b.build_stratified_sample(df, per * k, 5)
    parts = [f1b.shard_slice(f1b.build_stratified_sample(df, per * k, 5), (i, k)) for i in range(k)]
    ids = [set(p["TIC"]) for p in parts]
    assert sum(len(x) for x in ids) == len(set().union(*ids)) == len(full)     # no star in two shards
    assert set().union(*ids) == set(full["TIC"])                              # nothing dropped
    assert all(len(p) == per for p in parts)


def test_each_shard_keeps_the_brightness_mix():
    df, k = table(20000), 4
    full = f1b.build_stratified_sample(df, 400, 5)
    for i in range(k):
        part = f1b.shard_slice(full, (i, k))
        # five equal brightness bins of 400 stars: each shard gets close to a fifth from each bin
        bins = pd.qcut(df.set_index("TIC").loc[part["TIC"], "Tmag"], 5, labels=False)
        assert bins.value_counts(normalize=True).max() < 0.35


def test_draw_excludes_history_so_tomorrow_is_new_stars():
    df = table()
    day1 = f1b.build_stratified_sample(df, 200, 5)
    day2 = f1b.build_stratified_sample(df, 200, 5, exclude_ids=set(day1["TIC"]))
    assert not set(day1["TIC"]) & set(day2["TIC"])


def test_orchestrator_reads_the_file_f1b_writes():
    src = (Path(__file__).resolve().parent.parent / "f6_orchestrator.py").read_text(encoding="utf-8")
    assert 'proc / "sample_batch.csv"' in src and 'read_csv_safe(proc / "sample_500.csv")' not in src
