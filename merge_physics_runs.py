"""Merge the per-job outputs of the Physics workflow (.github/workflows/physics.yml).

  python merge_physics_runs.py <root> <parts_dir>

f26_<tic>.json  -> replaces those stars in data/processed/f26_ebfit.json (other stars are kept)
f29_*.json      -> data/processed/f29_benchmarks.json   (f29_benchmark.merge)
f30_*.json      -> data/processed/f30_injection.json    (f30_injection.merge)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import f29_benchmark
import f30_injection


def merge_f26(root, parts):
    dest = root / "data" / "processed" / "f26_ebfit.json"
    cur = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {"stars": {}}
    n = 0
    for p in sorted(Path(parts).rglob("f26_*.json")):
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
    print("f26 stars merged:", merge_f26(root, parts))
    if list(parts.rglob("f29_*.json")):
        print("f29:", json.dumps(f29_benchmark.merge(root, parts)["summary"]))
    if list(parts.rglob("f30_*.json")):
        print("f30:", json.dumps(f30_injection.merge(root, parts)["overall"]["trust_rule"]))


if __name__ == "__main__":
    main()
