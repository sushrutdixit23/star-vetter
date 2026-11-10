"""How much does a clear result from f14_novelty_extra.py actually tell us?

A star that matches nothing in six extra variable-star catalogs is only evidence
of novelty if those catalogs would have caught a star that IS known. This
measures that, on real known eclipsing binaries: it runs a sample of TESS
eclipsing binaries from Prsa et al. 2022 (VizieR J/ApJS/258/16), chosen to match
the candidates in brightness (Tmag 12-15.5), through exactly the same cross-match
code, and counts how many come back as already known.

  recall_period_match   fraction returned ALREADY_KNOWN (same star, matching period)
  recall_any_same_star  fraction with a same-star entry of any period
A clear result is only as strong as that recall: if it is 14%, then 86% of known
binaries also come back clear.

Stars for which any catalog query failed (INCOMPLETE) are left out of the
fractions and counted, never treated as clear.

Usage:  python f14_calibrate.py <root> [--n 450] [--seed 7] [--host URL]
Writes: data/processed/f14_recall_known_ebs.json   (read by export_predictions.py)
Cache:  data/processed/f14_cache/calibration/<catalog>.json
"""

import math
import os
import sys
import threading
import json
from pathlib import Path

import numpy as np
import pandas as pd

import f14_novelty_extra as f14

TMAG_RANGE = (12.0, 15.5)


def wilson(k, n, z=1.96):
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    root = Path(argv[0]).resolve()
    n, seed, host = 450, 7, f14.DEFAULT_HOST
    for i, a in enumerate(argv):
        if a == "--n":
            n = int(argv[i + 1])
        elif a == "--seed":
            seed = int(argv[i + 1])
        elif a == "--host":
            host = argv[i + 1]
    proc = root / "data" / "processed"
    cache_dir = proc / "f14_cache" / "calibration"
    cache_dir.mkdir(parents=True, exist_ok=True)

    from astroquery.mast import Catalogs
    from upstream import query_tic_chunked

    ebs = pd.read_csv(proc / "cat_tess_ebs_prsa2022.csv")
    tab = query_tic_chunked(lambda ids: Catalogs.query_criteria(catalog="Tic", ID=[int(i) for i in ids]),
                            [int(x) for x in ebs["TIC"]], chunk_size=300).to_pandas()[["ID", "ra", "dec", "Tmag"]]
    tab["ID"] = tab["ID"].astype(int)
    m = ebs.merge(tab, left_on="TIC", right_on="ID").dropna(subset=["ra", "dec", "Tmag"])
    m = m[(m["Tmag"] > TMAG_RANGE[0]) & (m["Tmag"] < TMAG_RANGE[1])]
    m = m.sample(min(n, len(m)), random_state=seed)
    stars = [{"tic": int(r.TIC), "tier": "KNOWN_EB", "ra": float(r.ra), "dec": float(r.dec),
              "periods": [float(r.tess_eb_period)], "tmag": float(r.Tmag)} for r in m.itertuples()]
    print(f"{len(stars)} known eclipsing binaries, Tmag {TMAG_RANGE[0]}-{TMAG_RANGE[1]}", flush=True)

    print(f"Self-test against {host} ...", flush=True)
    ok, problems = f14.self_test(host)
    if not ok:
        print("Self-test FAILED, not calibrating:\n  " + "\n  ".join(problems))
        return 3

    results = {}
    threads = [threading.Thread(target=f14.run_catalog, daemon=True, args=(
        c, stars, str(cache_dir / (c["key"] + ".json")), host, False, results, lambda msg: None))
        for c in f14.CATALOGS]
    [t.start() for t in threads]
    [t.join() for t in threads]
    _, per_star = f14.build_tables(stars, results)

    complete = per_star[per_star["verdict"] != "INCOMPLETE"]
    n_in = int(len(complete))
    k_match = int((complete["verdict"] == "ALREADY_KNOWN").sum())
    k_any = int(complete["verdict"].isin(["ALREADY_KNOWN", "KNOWN_VARIABLE_PERIOD_DIFFERS"]).sum())

    cand_path = proc / "f14_novelty_extra.csv"
    cand = pd.read_csv(cand_path) if cand_path.exists() else pd.DataFrame()
    cand_ok = cand[cand["verdict"] != "INCOMPLETE"] if not cand.empty else cand
    out = {
        "n_known_ebs": n_in,
        "n_incomplete_excluded": int(len(per_star) - n_in),
        "recall_period_match": k_match / n_in if n_in else None,
        "recall_period_match_ci95": wilson(k_match, n_in),
        "recall_any_same_star": k_any / n_in if n_in else None,
        "candidates_n": int(len(cand_ok)),
        "candidates_period_match_rate": (float((cand_ok["verdict"] == "ALREADY_KNOWN").mean())
                                         if len(cand_ok) else None),
        "source": "Prsa et al. 2022 known TESS eclipsing binaries, Tmag 12-15.5, run through the same cross-match code",
    }
    path = proc / "f14_recall_known_ebs.json"
    path.write_text(json.dumps(out, indent=1, allow_nan=False), encoding="utf-8", newline="\n")
    print(f"Known binaries returned ALREADY_KNOWN: {k_match}/{n_in} = {k_match / n_in:.1%} "
          f"(95% {out['recall_period_match_ci95'][0]:.1%}-{out['recall_period_match_ci95'][1]:.1%}); "
          f"any same-star entry: {k_any / n_in:.1%}")
    print(f"Candidates returned ALREADY_KNOWN: {out['candidates_period_match_rate']}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
