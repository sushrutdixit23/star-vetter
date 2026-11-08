import re
import sys
import time
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Cross-match of the candidates against published TESS eclipsing-binary
# catalogs that the older f4 / f14 checks did not cover, by TIC number.
#
# For each catalog this reports two numbers, because one alone misleads: how
# many candidates are IN the catalog, and how many are even inside its
# footprint (its parent sample). A catalog that searched only hot OBAF stars
# cannot confirm or deny a cool, faint candidate, so "0 matches" there says
# nothing about novelty.
#
# Catalogs from VizieR (TIC column only), cached under data/processed/:
#   IJspeert et al. 2021 EB list     J/A+A/652/A120/eb-cat   (parent: oba-cat)
#   IJspeert et al. 2024 EB list     J/A+A/691/A242/obaf-eb1 (parent: tessobaf)
#   Justesen & Albrecht 2021 EBs     J/ApJ/912/123/table2    (southern, year 1)
# Local copies from the survey's own ingestion:
#   Kostov et al. 2025 vetted new EBs (table 3) and known EBs (table 4)
#   Prsa et al. 2022 (cat_tess_ebs_prsa2022.csv)
# Not covered here: the 2024-2026 machine-learning TESS catalogs (Shan, Gao,
# Wang, Ding, Liu), the live Villanova catalog, Gaia DR4.

VIZIER = "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv?-source=%s&-out=TIC&-out.max=unlimited"
REMOTE = {
    "ijspeert2021_eb": ("J/A%2BA/652/A120/eb-cat", "IJspeert et al. 2021 (OBA eclipsing binaries)"),
    "ijspeert2024_eb": ("J/A%2BA/691/A242/obaf-eb1", "IJspeert et al. 2024 (OBAF eclipsing binaries)"),
    "justesen2021_eb": ("J/ApJ/912/123/table2", "Justesen & Albrecht 2021 (southern eclipsing binaries)"),
}
PARENTS = {
    "ijspeert2021_eb": ("J/A%2BA/652/A120/oba-cat", "ijspeert2021_parent"),
    "ijspeert2024_eb": ("J/A%2BA/691/A242/tessobaf", "ijspeert2024_parent"),
}


def parse_tics(text):
    """TIC numbers from a VizieR tab-separated download (comment lines skipped)."""
    out = set()
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and re.fullmatch(r"\d{5,10}", s):
            out.add(int(s))
    return out


def fetch_tics(source, cache, attempts=5, min_rows=100):
    """Download once and cache. The mirror sometimes answers with an empty
    table, so an answer with fewer than min_rows rows is retried, never cached."""
    if cache.exists():
        return parse_tics(cache.read_text(encoding="utf-8"))
    last = 0
    for i in range(attempts):
        try:
            req = urllib.request.Request(VIZIER % source, headers={"User-Agent": "star-vetter"})
            with urllib.request.urlopen(req, timeout=240) as r:
                tics = parse_tics(r.read().decode("utf-8", errors="replace"))
            last = len(tics)
            if last >= min_rows:
                cache.write_text("\n".join(str(t) for t in sorted(tics)) + "\n", encoding="utf-8", newline="\n")
                return tics
        except OSError:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError("download of %s kept returning too few rows (last %d)" % (source, last))


def build(candidates, catalogs, parents, labels, now=None):
    """candidates: set of TIC. catalogs/parents: name -> set of TIC."""
    rows = []
    for name, tics in catalogs.items():
        par = parents.get(name)
        rows.append({
            "key": name, "label": labels.get(name, name), "catalog_size": len(tics),
            "candidates_in_catalog": sorted(candidates & tics),
            "n_in_catalog": len(candidates & tics),
            "n_in_parent_sample": (len(candidates & par) if par is not None else None),
            "parent_size": (len(par) if par is not None else None),
        })
    return {
        "generated_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidates": len(candidates),
        "catalogs": rows,
        "reading": "n_in_parent_sample is how many candidates the catalog could even have found (its search footprint). "
                   "A catalog with a small footprint cannot show that a candidate is new.",
        "not_covered": ["2024-2026 machine-learning TESS catalogs (Shan, Gao, Wang, Ding, Liu)", "live Villanova catalog", "Gaia DR4"],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: py f16_tess_catalog_xmatch.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    proc = root / "data" / "processed"
    dash = json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))
    cands = {int(s["tic"]) for s in dash["sky"]}
    catalogs, parents, labels = {}, {}, {}
    for name, (src, label) in REMOTE.items():
        catalogs[name] = fetch_tics(src, proc / ("cat_%s_tics.txt" % name))
        labels[name] = label
    for name, (src, pname) in PARENTS.items():
        parents[name] = fetch_tics(src, proc / ("cat_%s_tics.txt" % pname))
    t3 = set(pd.read_parquet(proc / "table3_new_ebs.parquet", columns=["TIC"])["TIC"].astype(int))
    t4 = set(pd.read_parquet(proc / "table4_known_ebs.parquet", columns=["TIC"])["TIC"].astype(int))
    catalogs["kostov2025_vetted"] = t3 | t4
    labels["kostov2025_vetted"] = "Kostov et al. 2025 vetted EBs (tables 3 and 4)"
    pr = pd.read_csv(proc / "cat_tess_ebs_prsa2022.csv")
    col = [c for c in pr.columns if c.lower() in ("tic", "ticid", "tic_id")][0]
    catalogs["prsa2022"] = set(pr[col].dropna().astype(int))
    labels["prsa2022"] = "Prsa et al. 2022 (2-minute targets, sectors 1-26)"
    out = build(cands, catalogs, parents, labels)
    path = root / "site" / "public" / "data" / "tess_catalog_xmatch.json"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    for r in out["catalogs"]:
        print("%-52s in catalog %3d   in its search footprint %s" % (r["label"], r["n_in_catalog"], r["n_in_parent_sample"]))
    print("Written: %s" % path)


if __name__ == "__main__":
    main()
