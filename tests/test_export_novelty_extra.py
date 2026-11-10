import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import export_novelty_extra as en  # noqa: E402


def test_build_splits_lists_and_keeps_verdicts(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame([
        {"tic": 1, "tier": "CLEAN", "verdict": "ALREADY_KNOWN", "matched_catalogs": "atlas,ztf", "known_other_period": None, "nearby_catalogs": None},
        {"tic": 2, "tier": "CLEAN", "verdict": "NO_MATCH", "matched_catalogs": None, "known_other_period": None, "nearby_catalogs": None},
        {"tic": 3, "tier": "CLEAN", "verdict": "KNOWN_VARIABLE_PERIOD_DIFFERS", "matched_catalogs": None, "known_other_period": "atlas", "nearby_catalogs": "ztf"},
    ]).to_csv(p, index=False)
    out = en.build(p)
    assert out["1"]["matched_catalogs"] == ["atlas", "ztf"] and out["1"]["verdict"] == "ALREADY_KNOWN"
    assert out["2"] == {"verdict": "NO_MATCH", "matched_catalogs": [], "known_other_period": [], "nearby_catalogs": []}
    assert out["3"]["known_other_period"] == ["atlas"] and out["3"]["nearby_catalogs"] == ["ztf"]


def test_published_file_covers_every_candidate():
    import json
    root = Path(__file__).resolve().parent.parent
    d = json.loads((root / "site/public/data/novelty_extra.json").read_text(encoding="utf-8"))["stars"]
    tics = {p.stem[3:] for p in (root / "site/public/data/detail").glob("TIC*.json")}
    assert tics <= set(d)
