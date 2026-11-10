"""Offline tests for freeze_predictions.py: the bundle must be reproducible,
tamper-evident, and refuse to freeze anything that is not a real forecast."""
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import freeze_predictions as fp  # noqa: E402

NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)


def payload(utc="2027-03-15 05:49:00", n_stars=2):
    stars = [{"tic": 100 + i, "grade": "VALIDATED", "ephemeris": {"period_days": 3.0, "t0_btjd": 2000.0},
              "predictions": [{"sector": 115, "cycle": 900, "t_btjd": 4479.7, "utc": utc, "sigma_min": 2.0, "approximate": False}]}
             for i in range(n_stars)]
    return {"counts": {"candidates_considered": 10, "listed": n_stars, "listed_validated": n_stars,
                       "listed_unvalidated": 0, "rejected_failed_holdout": 0},
            "conventions": {"outcome_rule": "rule", "grades": "grades", "time_scale": "ts", "sigma": "sg"},
            "selection_rule": ["a", "b"], "excluded": {"X": 1}, "stars": stars}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "site" / "public" / "data").mkdir(parents=True)
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "site" / "public" / "data" / "predictions.json").write_text(json.dumps(payload()), encoding="utf-8")
    (tmp_path / "data" / "processed" / "f13_ephemerides.csv").write_text("tic\n100\n", encoding="utf-8")
    (tmp_path / "f13_ephemeris.py").write_text("# code\n", encoding="utf-8")
    return tmp_path


def test_freeze_then_verify_passes_for_folder_and_zip(root, tmp_path):
    code, msgs, res = fp.build(root, tmp_path / "out", now=NOW)
    assert code == 0 and res is not None
    assert fp.verify(res["bundle"])[0] and fp.verify(res["zip"])[0]
    assert {"predictions.json", "predictions.csv", "data/f13_ephemerides.csv", "code/f13_ephemeris.py"} <= set(res["manifest"]["files"])
    assert "README.txt" not in res["manifest"]["files"]      # it quotes the bundle hash, so it cannot be inside it


def test_changing_any_frozen_file_is_detected(root, tmp_path):
    _, _, res = fp.build(root, tmp_path / "out", now=NOW)
    p = res["bundle"] / "predictions.json"
    p.write_text(p.read_text(encoding="utf-8").replace("2027-03-15", "2027-03-16"), encoding="utf-8")
    ok, msgs = fp.verify(res["bundle"])
    assert not ok and any(m.startswith("CHANGED") and "predictions.json" in m for m in msgs)


def test_a_tampered_zip_is_detected(root, tmp_path):
    _, _, res = fp.build(root, tmp_path / "out", now=NOW)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(res["zip"]) as zin, zipfile.ZipFile(bad, "w") as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n.endswith("predictions.csv"):
                data = data.replace(b"4479.7", b"4480.7")
            zout.writestr(n, data)
    assert not fp.verify(bad)[0]


def test_a_deleted_file_is_detected(root, tmp_path):
    _, _, res = fp.build(root, tmp_path / "out", now=NOW)
    (res["bundle"] / "code" / "f13_ephemeris.py").unlink()
    ok, msgs = fp.verify(res["bundle"])
    assert not ok and any(m.startswith("MISSING") for m in msgs)


def test_same_inputs_give_the_same_bundle_hash_and_zip_bytes(root, tmp_path):
    _, _, a = fp.build(root, tmp_path / "o1", now=NOW)
    _, _, b = fp.build(root, tmp_path / "o2", now=NOW)
    assert a["manifest"]["bundle_sha256"] == b["manifest"]["bundle_sha256"]
    assert a["zip"].read_bytes() == b["zip"].read_bytes()


def test_refuses_an_empty_forecast(root, tmp_path):
    (root / "site" / "public" / "data" / "predictions.json").write_text(json.dumps(payload(n_stars=0)), encoding="utf-8")
    code, msgs, res = fp.build(root, tmp_path / "out", now=NOW)
    assert code == 1 and res is None and any("no stars" in m for m in msgs)


def test_refuses_predictions_that_are_already_in_the_past(root, tmp_path):
    (root / "site" / "public" / "data" / "predictions.json").write_text(json.dumps(payload(utc="2026-10-01 00:00:00")), encoding="utf-8")
    code, msgs, res = fp.build(root, tmp_path / "out", now=NOW)
    assert code == 1 and any("already in the past" in m for m in msgs)
    assert not (tmp_path / "out").exists()


def test_warns_when_year9_has_begun_but_still_freezes(root, tmp_path):
    late = datetime(2026, 12, 1, tzinfo=timezone.utc)
    code, msgs, res = fp.build(root, tmp_path / "out", now=late)
    assert code == 0 and any("Year 9 has already begun" in m for m in msgs)


def test_never_overwrites_an_existing_bundle(root, tmp_path):
    assert fp.build(root, tmp_path / "out", now=NOW)[0] == 0
    code, msgs, _ = fp.build(root, tmp_path / "out", now=NOW)
    assert code == 1 and any("already exists" in m for m in msgs)


def test_missing_predictions_file_is_refused(tmp_path):
    code, msgs, _ = fp.build(tmp_path, tmp_path / "out", now=NOW)
    assert code == 1 and "export_predictions.py" in msgs[0]


def test_dirty_git_tree_is_refused_unless_allowed(root, tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-q", "-m", "x")
    (root / "f13_ephemeris.py").write_text("# changed\n", encoding="utf-8")
    code, msgs, _ = fp.build(root, tmp_path / "o1", now=NOW)
    assert code == 1 and any("uncommitted" in m for m in msgs)
    code, msgs, res = fp.build(root, tmp_path / "o2", allow_dirty=True, now=NOW)
    assert code == 0 and any("DIRTY" in m for m in msgs) and res["manifest"]["git"]["dirty"] is True


def test_readme_is_plain_ascii_and_states_the_grading_rule(root, tmp_path):
    _, _, res = fp.build(root, tmp_path / "out", now=NOW)
    text = (res["bundle"] / "README.txt").read_bytes()
    text.decode("ascii")
    assert b"rule" in text and res["manifest"]["bundle_sha256"].encode() in text
