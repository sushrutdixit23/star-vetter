"""Merge the per-job outputs of the Physics workflow (.github/workflows/physics.yml).

  python merge_physics_runs.py <root> <parts_dir>

f26_<tic>.json  -> replaces those stars in data/processed/f26_ebfit.json (other stars are kept)
f29_*.json      -> data/processed/f29_benchmarks.json   (f29_benchmark.merge)
f30_*.json      -> data/processed/f30_injection.json    (f30_injection.merge)
f26v2_<tic>.json -> data/processed/f26_ebfit_v2.json     (noise model v2; the site keeps reading f26_ebfit.json)
f29v2_*.json    -> data/processed/f29_benchmarks_v2.json
f30v2_*.json    -> data/processed/f30_injection_v2.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import f29_benchmark
import f30_injection


def merge_f26(root, parts, tag=""):
    dest = root / "data" / "processed" / ("f26_ebfit%s.json" % (("_" + tag) if tag else ""))
    cur = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {"stars": {}}
    n = 0
    for p in sorted(Path(parts).rglob("f26%s_*.json" % tag)):
        for tic, r in json.loads(p.read_text(encoding="utf-8"))["stars"].items():
            cur["stars"][tic] = r
            n += 1
    if n:
        cur["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur["note"] = ("chains extended until 20 autocorrelation times after burn-in where the step cap allowed "
                       "(Physics workflow); see each star's steps and converged fields")
        dest.write_text(json.dumps(cur, indent=1) + "\n", encoding="utf-8", newline="\n")
    return n


def main():
    root, parts = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    for tag in ("", "v2"):
        label = tag or "v1"
        print("f26 stars merged (%s):" % label, merge_f26(root, parts, tag))
        if list(parts.rglob("f29%s_*.json" % tag)):
            print("f29 (%s):" % label, json.dumps(f29_benchmark.merge(root, parts, tag)["summary"]))
        if list(parts.rglob("f30%s_*.json" % tag)):
            print("f30 (%s):" % label, json.dumps(f30_injection.merge(root, parts, tag)["overall"]["trust_rule"]))


if __name__ == "__main__":
    main()
