"""Publish the six-catalog cross-match verdict for every candidate.

Reads data/processed/f14_novelty_extra.csv (f14_novelty_extra.py) and writes
site/public/data/novelty_extra.json so every candidate page and the candidate
list can say when a star is already listed. Before this file existed the site
said "no match in the catalogs searched" for all 307 stars, including the 9
that the extra cross-match found already listed in ATLAS.

Usage:  python export_novelty_extra.py <project_root>
"""

import json
import sys
from pathlib import Path

import pandas as pd


def _split(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return []
    return [x.strip() for x in str(v).split(",") if x.strip()]


NOT_CHECKED = {"verdict": "NOT_CHECKED", "matched_catalogs": [], "known_other_period": [], "nearby_catalogs": []}


def build(csv_path, candidate_tics=None):
    """Verdict per star. A candidate with no row in the CSV (the cross-match did not run, e.g. the VizieR mirror was
    down) gets an explicit NOT_CHECKED entry: a missing answer is stated, never left out and never read as "no match"."""
    df = pd.read_csv(csv_path)
    out = {}
    for r in df.itertuples(index=False):
        out[str(int(r.tic))] = {
            "verdict": str(r.verdict),
            "matched_catalogs": _split(r.matched_catalogs),
            "known_other_period": _split(r.known_other_period),
            "nearby_catalogs": _split(r.nearby_catalogs),
        }
    for tic in candidate_tics or ():
        out.setdefault(str(int(tic)), dict(NOT_CHECKED))
    return out


def main(root):
    root = Path(root)
    tics = [int(p.stem[3:]) for p in (root / "site/public/data/detail").glob("TIC*.json")]
    stars = build(root / "data/processed/f14_novelty_extra.csv", tics)
    counts = {}
    for v in stars.values():
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    doc = {"counts": counts, "stars": stars}
    path = root / "site/public/data/novelty_extra.json"
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(counts, "->", path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
