"""Does the VizieR-mirror cross-match give the same answers as CDS XMatch did?

The committed data/processed/f4f_novelty_results.csv was produced by the XMatch path before it went down. This
re-asks the same three questions (VSX, Gaia DR3 eclipsing-binary table, Gaia DR3 classifier table) for the same
stars through the Harvard-CfA VizieR mirror (crossmatch.py) and counts every difference. Differences are listed,
not hidden: the mirror can lag CDS, and VSX gains entries every day.

Usage: python validate_crossmatch_fallback.py <root> [--coords FILE]   -> data/processed/crossmatch_fallback_check.json
  --coords FILE   CSV with TIC,ra,dec to use instead of asking MAST (a cache)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import crossmatch as cx
from f4_novelty import MATCH_RADIUS_ARCSEC
from upstream import query_tic_chunked

CATALOGS = {"vsx": "B/vsx/vsx", "gaia_veb": "I/358/veb", "gaia_class": "I/358/vclassre"}


def coords_for(tics, cache):
    if cache and Path(cache).exists():
        return pd.read_csv(cache)
    from astroquery.mast import Catalogs
    t = query_tic_chunked(lambda ids: Catalogs.query_criteria(catalog="Tic", ID=ids), tics, timeout=180)
    d = t[["ID", "ra", "dec"]].to_pandas().rename(columns={"ID": "TIC"})
    d["TIC"] = d["TIC"].astype(int)
    if cache:
        d.to_csv(cache, index=False)
    return d


def _blank(x):
    return x is None or (isinstance(x, float) and np.isnan(x)) or (isinstance(x, str) and not x.strip())


def same(a, b):
    """Equal values; a missing value (None, NaN or an empty string) equals another missing value."""
    a_nan, b_nan = _blank(a), _blank(b)
    if a_nan or b_nan:
        return a_nan and b_nan
    try:
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def main():
    args = sys.argv[1:]
    root = Path(args[0]).resolve()
    cache = args[args.index("--coords") + 1] if "--coords" in args else None
    ref = pd.read_csv(root / "data" / "processed" / "f4f_novelty_results.csv")
    xy = coords_for([int(x) for x in ref["TIC"]], cache)
    merged = ref.merge(xy, on="TIC", how="inner")
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "server": cx.MIRROR_SERVER,
           "radius_arcsec": MATCH_RADIUS_ARCSEC, "n_stars": int(len(merged)), "n_reference_rows": int(len(ref)),
           "reference": "data/processed/f4f_novelty_results.csv (produced through CDS XMatch before the outage)", "catalogs": {}}
    results = {k: cx.crossmatch(merged[["TIC", "ra", "dec"]], src, MATCH_RADIUS_ARCSEC) for k, src in CATALOGS.items()}
    checks = {"vsx": [("vsx_match", None), ("vsx_name", "Name"), ("vsx_type", "Type"), ("vsx_period", "Period")],
              "gaia_veb": [("gaia_veb_match", None)],
              "gaia_class": [("gaia_class_match", None), ("gaia_class", "Class"), ("gaia_class_score", "ClassSc")]}
    for key, fields in checks.items():
        r = results[key].set_index("TIC")
        diffs = []
        n_match_ref = n_match_new = 0
        for _, row in merged.iterrows():
            tic = int(row["TIC"])
            hit = tic in r.index
            n_match_new += hit
            n_match_ref += bool(row[fields[0][0]])
            if bool(row[fields[0][0]]) != hit:
                diffs.append({"TIC": tic, "field": fields[0][0], "reference": bool(row[fields[0][0]]), "mirror": hit})
                continue
            if not hit:
                continue
            for ref_col, cat_col in fields[1:]:
                a, b = r.loc[tic, cat_col] if cat_col in r.columns else None, row[ref_col]
                if not same(a, b):
                    diffs.append({"TIC": tic, "field": ref_col, "reference": None if pd.isna(b) else str(b),
                                  "mirror": None if (a is None or pd.isna(a)) else str(a)})
        out["catalogs"][key] = {"source": CATALOGS[key], "matches_reference": n_match_ref, "matches_mirror": n_match_new,
                                "n_differences": len(diffs), "differences": diffs[:40]}
    out["total_differences"] = int(sum(c["n_differences"] for c in out["catalogs"].values()))
    p = root / "data" / "processed" / "crossmatch_fallback_check.json"
    p.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "differences"} for k, v in out["catalogs"].items()}, indent=1))
    print("total differences:", out["total_differences"])


if __name__ == "__main__":
    main()
