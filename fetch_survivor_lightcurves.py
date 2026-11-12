import sys
import json
from pathlib import Path

import pandas as pd

import f13_ephemeris as f13

# Downloads (once) the TESS light curves of every survivor that has no cached copy yet, into the
# same cache f13 uses, so later measurements (eccentricity, timing) never need MAST again.
# Usage: py fetch_survivor_lightcurves.py <root> [shard] [n_shards]


def main():
    root = Path(sys.argv[1]).resolve()
    shard = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    proc = root / "data" / "processed"
    sky = json.loads((root / "site" / "public" / "data" / "dashboard.json").read_text(encoding="utf-8"))["sky"]
    man = pd.read_csv(proc / "f2c_manifest.csv")
    author_of = dict(zip(man["TIC"], man["author_used"])) if "author_used" in man.columns else {}
    todo = sorted(int(r["tic"]) for r in sky if not (proc / "f13_lc_cache" / ("TIC%d.npz" % int(r["tic"]))).exists())
    todo = [t for i, t in enumerate(todo) if i % n == shard]
    print("shard %d: %d stars to fetch" % (shard, len(todo)), flush=True)
    for i, tic in enumerate(todo):
        try:
            lcs = f13.load_or_fetch_lightcurves(tic, author_of.get(tic), print, proc / "f13_lc_cache")
            print("%d/%d TIC %d: %d sectors" % (i + 1, len(todo), tic, len(lcs)), flush=True)
        except Exception as e:  # noqa: BLE001 - keep going, report it
            print("%d/%d TIC %d: FAILED %r" % (i + 1, len(todo), tic, e), flush=True)


if __name__ == "__main__":
    main()
