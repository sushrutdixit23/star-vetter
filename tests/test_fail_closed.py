"""
Tests for the 2026-11-07 fail-closed changes (see upstream.py).

Run from the repo root:   py -m pytest tests -q
They need astroquery installed but make NO network calls: every remote
service is replaced by a stub.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from astropy.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import upstream  # noqa: E402
import f4f_novelty  # noqa: E402
import diag_blend  # noqa: E402
import f6_orchestrator  # noqa: E402


# ---------------------------------------------------------------- helpers

@pytest.fixture(autouse=True)
def _no_network_probe(monkeypatch):
    """f4f_novelty asks upstream which VizieR host to use; never let a test do that over the network."""
    monkeypatch.setattr(f4f_novelty, "pick_vizier_server", lambda *a, **k: "test.vizier.invalid")
    monkeypatch.delenv("STAR_VETTER_SKIP_XMATCH", raising=False)
    monkeypatch.delenv("STAR_VETTER_VIZIER_SERVER", raising=False)


def make_project(tmp_path, n_stars=12):
    proc = tmp_path / "data" / "processed"
    proc.mkdir(parents=True)
    pd.DataFrame({
        "TIC": list(range(1000, 1000 + n_stars)),
        "status": "OK",
        "depth_flagged_implausible": False,
        "bls_period": 2.5, "bls_snr": 100.0, "bls_depth": 0.01,
        "n_eclipses_observed": 10, "gap_edge_suspect": False,
    }).to_csv(proc / "f3i_vetting_results.csv", index=False)
    return tmp_path


def fake_tic(catalog, ID):
    ids = list(ID)
    return Table({"ID": ids, "ra": [10.0 + i * 0.01 for i in range(len(ids))],
                  "dec": [20.0] * len(ids), "Tmag": [12.0] * len(ids),
                  "contratio": [0.0] * len(ids)})


def empty_xmatch(**kwargs):
    return Table({"TIC": [], "angDist": []})


# ---------------------------------------------------------------- upstream.py

def test_chunked_lookup_splits_and_recombines():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return fake_tic("Tic", ids)

    out = upstream.query_tic_chunked(fetch, list(range(10)), chunk_size=4, log=lambda *_: None)
    assert [len(c) for c in calls] == [4, 4, 2]
    assert list(out["ID"]) == list(range(10))


def test_chunked_lookup_raises_instead_of_returning_partial_data():
    attempts = {"n": 0}

    def fetch(ids):
        attempts["n"] += 1
        raise ConnectionError("down")

    with pytest.raises(upstream.UpstreamDown):
        upstream.query_tic_chunked(fetch, [1, 2, 3], chunk_size=2, retries=2, delay=0)
    assert attempts["n"] == 3  # first chunk only: 1 try + 2 retries, then give up


def test_breaker_trips_on_consecutive_failures_only():
    b = upstream.FailureBreaker(3)
    assert not b.record(False)
    assert not b.record(False)
    assert not b.record(True)    # a success resets the count
    assert not b.record(False)
    assert not b.record(False)
    assert b.record(False)


# ---------------------------------------------------------------- f4f_novelty

def run_f4f(project, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["f4f_novelty.py", str(project)])
    monkeypatch.setattr(f4f_novelty.time, "sleep", lambda *_: None)
    monkeypatch.setattr(f4f_novelty, "pick_vizier_server", lambda *a, **k: "test.vizier.invalid")
    monkeypatch.delenv("STAR_VETTER_SKIP_XMATCH", raising=False)
    with pytest.raises(SystemExit) as exc:
        f4f_novelty.main()
    return exc.value.code


def test_f4f_xmatch_outage_writes_nothing_and_exits_3(tmp_path, monkeypatch):
    """XMatch AND the VizieR fallback both down: exit 3, previous results untouched."""
    project = make_project(tmp_path)
    out = project / "data" / "processed" / "f4f_novelty_results.csv"
    out.write_text("TIC,verdict\n1000,KNOWN_OTHER_TYPE\n", encoding="utf-8")  # last good result

    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", fake_tic)
    calls = {"n": 0, "vizier": 0}

    def dead_xmatch(**kwargs):
        calls["n"] += 1
        raise TimeoutError("XMatch down")

    def dead_vizier(*a, **k):
        calls["vizier"] += 1
        raise upstream.UpstreamDown("mirror down too")

    monkeypatch.setattr(f4f_novelty.XMatch, "query", dead_xmatch)
    monkeypatch.setattr(f4f_novelty.cx, "crossmatch", dead_vizier)

    assert run_f4f(project, monkeypatch) == upstream.EXIT_UPSTREAM_DOWN
    # the previous good verdicts must be untouched, not overwritten with "no matches"
    assert out.read_text(encoding="utf-8") == "TIC,verdict\n1000,KNOWN_OTHER_TYPE\n"
    # gave up on the first dead catalog (1 try + retries) instead of timing out on all three,
    # then asked the fallback once, which also failed on its first catalog
    assert calls["n"] == f4f_novelty.XMATCH_RETRIES + 1
    assert calls["vizier"] == 1
    assert not (project / "data" / "processed" / "f4f_crossmatch_path.json").exists()


def test_f4f_falls_back_to_vizier_when_xmatch_is_down(tmp_path, monkeypatch):
    """XMatch down, VizieR answering: the run completes, the three catalogs all come from the fallback, and the
    result records which path was used. A catalogued star must stay catalogued (not become NOVEL)."""
    project = make_project(tmp_path, n_stars=12)
    out = project / "data" / "processed" / "f4f_novelty_results.csv"
    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", fake_tic)

    def dead_xmatch(**kwargs):
        raise TimeoutError("XMatch down")

    asked = []

    def vizier_xmatch(df, source, radius, server=None, **k):
        asked.append((source, server))
        if source == "B/vsx/vsx":      # star 1003 is a known variable in VSX
            return pd.DataFrame({"TIC": [1003], "angDist": [0.4], "Name": ["XX Test"], "Type": ["EB"], "Period": [2.5]})
        return pd.DataFrame({"TIC": [], "angDist": []})

    class QuietVizier:
        def __init__(self, *a, **k):
            pass

        def query_region(self, *a, **k):
            return []

    monkeypatch.setattr(f4f_novelty.XMatch, "query", dead_xmatch)
    monkeypatch.setattr(f4f_novelty.cx, "crossmatch", vizier_xmatch)
    monkeypatch.setattr(f4f_novelty, "Vizier", QuietVizier)
    monkeypatch.setattr(f4f_novelty, "load_tess_eb", lambda *a, **k: None)
    monkeypatch.setattr(f4f_novelty, "load_toi", lambda *a, **k: None)
    monkeypatch.setenv("STAR_VETTER_SKIP_XMATCH", "")
    monkeypatch.setattr(sys, "argv", ["f4f_novelty.py", str(project)])
    monkeypatch.setattr(f4f_novelty.time, "sleep", lambda *_: None)
    monkeypatch.setattr(f4f_novelty, "pick_vizier_server", lambda *a, **k: "test.vizier.invalid")

    f4f_novelty.main()

    res = pd.read_csv(out).set_index("TIC")
    assert len(res) == 12
    assert bool(res.loc[1003, "vsx_match"]) and res.loc[1003, "vsx_name"] == "XX Test"
    assert res.loc[1003, "verdict"] != "NOVEL"
    assert (res.drop(index=1003)["verdict"] == "NOVEL").all()
    assert [a[0] for a in asked] == ["B/vsx/vsx", "I/358/veb", "I/358/vclassre"]
    assert {a[1] for a in asked} == {"test.vizier.invalid"}
    path = json.loads((project / "data" / "processed" / "f4f_crossmatch_path.json").read_text(encoding="utf-8"))
    assert path["path"].startswith("VizieR")


def test_f4f_skips_xmatch_when_preflight_said_it_is_down(tmp_path, monkeypatch):
    project = make_project(tmp_path, n_stars=12)
    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", fake_tic)
    tried = {"xmatch": 0}

    def xmatch(**kwargs):
        tried["xmatch"] += 1
        return empty_xmatch()

    monkeypatch.setattr(f4f_novelty.XMatch, "query", xmatch)
    monkeypatch.setattr(f4f_novelty.cx, "crossmatch", lambda df, source, radius, **k: pd.DataFrame({"TIC": [], "angDist": []}))
    monkeypatch.setattr(f4f_novelty, "Vizier", type("Q", (), {"__init__": lambda self, *a, **k: None,
                                                              "query_region": lambda self, *a, **k: []}))
    monkeypatch.setattr(f4f_novelty, "load_tess_eb", lambda *a, **k: None)
    monkeypatch.setattr(f4f_novelty, "load_toi", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["f4f_novelty.py", str(project)])
    monkeypatch.setattr(f4f_novelty.time, "sleep", lambda *_: None)
    monkeypatch.setattr(f4f_novelty, "pick_vizier_server", lambda *a, **k: "test.vizier.invalid")
    monkeypatch.setenv("STAR_VETTER_SKIP_XMATCH", "1")

    f4f_novelty.main()
    assert tried["xmatch"] == 0


def test_f4f_stops_when_no_vizier_server_answers(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", fake_tic)
    monkeypatch.setattr(f4f_novelty.XMatch, "query", empty_xmatch)
    monkeypatch.setattr(sys, "argv", ["f4f_novelty.py", str(project)])
    monkeypatch.setattr(f4f_novelty.time, "sleep", lambda *_: None)
    monkeypatch.setattr(f4f_novelty, "pick_vizier_server", lambda *a, **k: None)
    with pytest.raises(SystemExit) as exc:
        f4f_novelty.main()
    assert exc.value.code == upstream.EXIT_UPSTREAM_DOWN
    assert not (project / "data" / "processed" / "f4f_novelty_results.csv").exists()


def test_f4f_asassn_outage_trips_breaker_and_writes_nothing(tmp_path, monkeypatch):
    project = make_project(tmp_path, n_stars=30)
    out = project / "data" / "processed" / "f4f_novelty_results.csv"

    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", fake_tic)
    monkeypatch.setattr(f4f_novelty.XMatch, "query", empty_xmatch)
    queried = {"n": 0}

    class DeadVizier:
        def __init__(self, *a, **k):
            pass

        def query_region(self, *a, **k):
            queried["n"] += 1
            raise TimeoutError("Vizier down")

    monkeypatch.setattr(f4f_novelty, "Vizier", DeadVizier)

    assert run_f4f(project, monkeypatch) == upstream.EXIT_UPSTREAM_DOWN
    assert not out.exists()
    # stopped after the breaker limit, did not grind through all 30 stars
    assert queried["n"] == f4f_novelty.ASASSN_MAX_CONSECUTIVE_FAILURES * (f4f_novelty.ASASSN_RETRIES + 1)  # tries per star


def test_f4f_happy_path_still_writes_verdicts(tmp_path, monkeypatch):
    """Services up and nothing catalogued: every star is NOVEL and the results
    file is written, i.e. the fail-closed changes did not break normal runs."""
    project = make_project(tmp_path, n_stars=12)
    out = project / "data" / "processed" / "f4f_novelty_results.csv"

    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", fake_tic)
    monkeypatch.setattr(f4f_novelty.XMatch, "query", empty_xmatch)

    class QuietVizier:
        def __init__(self, *a, **k):
            pass

        def query_region(self, *a, **k):
            return []   # no ASAS-SN match

    monkeypatch.setattr(f4f_novelty, "Vizier", QuietVizier)
    monkeypatch.setattr(f4f_novelty, "load_tess_eb", lambda *a, **k: None)
    monkeypatch.setattr(f4f_novelty, "load_toi", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["f4f_novelty.py", str(project)])
    monkeypatch.setattr(f4f_novelty.time, "sleep", lambda *_: None)

    f4f_novelty.main()

    res = pd.read_csv(out)
    assert len(res) == 12
    assert set(res["verdict"]) == {"NOVEL"}


def test_f4f_tic_outage_exits_3(tmp_path, monkeypatch):
    project = make_project(tmp_path)

    def dead_tic(catalog, ID):
        raise ConnectionError("MAST down")

    monkeypatch.setattr(f4f_novelty.Catalogs, "query_criteria", dead_tic)
    monkeypatch.setattr(upstream.time, "sleep", lambda *_: None)
    assert run_f4f(project, monkeypatch) == upstream.EXIT_UPSTREAM_DOWN


# ---------------------------------------------------------------- diag_blend

def test_diag_blend_tic_outage_exits_3(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    pd.DataFrame({"TIC": [1000, 1001], "verdict": ["NOVEL", "NOVEL"],
                  "bls_period": [2.5, 2.5], "bls_depth": [0.01, 0.01]}
                 ).to_csv(project / "data" / "processed" / "f4f_novelty_results.csv", index=False)

    def dead_tic(catalog, ID):
        raise ConnectionError("MAST down")

    monkeypatch.setattr(diag_blend.Catalogs, "query_criteria", dead_tic)
    monkeypatch.setattr(upstream.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["diag_blend.py", str(project)])
    with pytest.raises(SystemExit) as exc:
        diag_blend.main()
    assert exc.value.code == upstream.EXIT_UPSTREAM_DOWN
    assert not (project / "data" / "processed" / "diag_blend_results.csv").exists()


# ---------------------------------------------------------------- orchestrator

def test_orchestrator_does_not_retry_exit_3(tmp_path):
    (tmp_path / "down.py").write_text("import sys\nprint('service down')\nsys.exit(3)\n", encoding="utf-8")
    lines = []
    with open(tmp_path / "log.txt", "w", encoding="utf-8") as logf:
        status, _, attempts = f6_orchestrator.run_stage(
            "stub stage", "down.py", tmp_path, lines.append, logf)
    assert status == "failed"
    assert attempts == 1   # NOT 3: retrying cannot fix a dead service
    assert any("not retrying" in str(line).lower() for line in lines)


def test_orchestrator_still_retries_ordinary_crashes(tmp_path):
    (tmp_path / "crash.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    f6_orchestrator.RETRY_DELAY_SEC = 0
    with open(tmp_path / "log.txt", "w", encoding="utf-8") as logf:
        status, _, attempts = f6_orchestrator.run_stage(
            "stub stage", "crash.py", tmp_path, lambda *_: None, logf)
    assert status == "failed"
    assert attempts == f6_orchestrator.MAX_RETRIES
