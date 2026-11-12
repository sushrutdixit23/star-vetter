import sys
import tarfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import merge_shards as ms  # noqa: E402


def write(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def make_root(tmp, manifest_tics, vet_tics):
    proc = tmp / "data" / "processed"
    write(proc / "f2c_manifest.csv", pd.DataFrame({"TIC": manifest_tics, "status": "OK"}))
    write(proc / "f3i_vetting_results.csv", pd.DataFrame({"TIC": vet_tics, "status": "OK", "depth_flagged_implausible": False}))
    return tmp


def test_union_keeps_existing_rows_and_adds_only_new_tics():
    base = pd.DataFrame({"TIC": [1, 2], "x": [10, 20]})
    other = pd.DataFrame({"TIC": [2, 3], "x": [99, 30]})
    out = ms.union_by_tic(base, [other])
    assert out["TIC"].tolist() == [1, 2, 3]
    assert out.loc[out.TIC == 2, "x"].item() == 20          # existing row wins, never overwritten


def test_union_is_idempotent():
    base = pd.DataFrame({"TIC": [1, 2]})
    other = pd.DataFrame({"TIC": [3, 4]})
    once = ms.union_by_tic(base, [other])
    twice = ms.union_by_tic(once, [other])
    assert once.equals(twice)


def test_pixel_table_keeps_a_control_and_a_candidate_row_per_tic():
    base = pd.DataFrame({"TIC": [1], "role": ["control"], "verdict": ["ON_TARGET"]})
    other = pd.DataFrame({"TIC": [1, 1], "role": ["control", "candidate"], "verdict": ["X", "ON_TARGET"]})
    out = ms.union_by_tic(base, [other])
    assert sorted(zip(out.TIC, out.role)) == [(1, "candidate"), (1, "control")]


def test_merge_of_two_shards_adds_disjoint_stars_and_history(tmp_path):
    root = make_root(tmp_path / "root", [1, 2], [1, 2])
    shards = tmp_path / "shards"
    for name, tics in (("shard-0", [10, 11]), ("shard-1", [20, 21, 22])):
        d = shards / name
        make_root(d, tics, tics)
        hist = d / "data" / "processed" / "sample_history"
        hist.mkdir(parents=True)
        (hist / ("sample_150_%s.csv" % name)).write_text("TIC\n" + "\n".join(map(str, tics)) + "\n")
        runs = d / "data" / "runs"
        runs.mkdir(parents=True)
        (runs / "20261111_010101.json").write_text("{}")
    s = ms.merge(root, ms.unpack(shards, tmp_path / "scratch"))
    assert s["before"]["sampled"] == 2 and s["after"]["sampled"] == 7
    assert s["added_rows"]["data/processed/f2c_manifest.csv"] == 5
    assert s["new_sample_history_files"] == 2
    assert len(list((root / "data" / "runs").glob("*.json"))) == 2     # same file name from two shards, both kept
    again = ms.merge(root, ms.unpack(shards, tmp_path / "scratch2"))
    assert again["after"] == s["after"]                                # merging again changes nothing


def test_tarball_shards_are_unpacked_and_unsafe_members_refused(tmp_path):
    d = tmp_path / "build"
    make_root(d, [5], [5])
    shards = tmp_path / "shards"
    shards.mkdir()
    with tarfile.open(shards / "shard-0.tgz", "w:gz") as tf:
        tf.add(d / "data", arcname="data")
    dirs = ms.unpack(shards, tmp_path / "scratch")
    assert (dirs[0] / "data" / "processed" / "f2c_manifest.csv").exists()
    bad = tmp_path / "bad"
    bad.mkdir()
    evil = tmp_path / "x.txt"
    evil.write_text("x")
    with tarfile.open(bad / "shard-0.tgz", "w:gz") as tf:
        tf.add(evil, arcname="../escape.txt")
    with pytest.raises(ValueError):
        ms.unpack(bad, tmp_path / "scratch3")


def test_render_reports_what_was_added():
    s = {"before": dict(sampled=10, usable_light_curves=8, statistically_passing=4, novel=2, pixel_checked=1, on_target=1),
         "after": dict(sampled=20, usable_light_curves=15, statistically_passing=7, novel=3, pixel_checked=2, on_target=1),
         "added_rows": {}, "new_sample_history_files": 3, "shards": [{}, {}, {}]}
    md = ms.render(s, tests="267 passed")
    assert "+10" in md and "267 passed" in md and md.isascii()
