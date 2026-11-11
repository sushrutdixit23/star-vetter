"""Merge the results of parallel pipeline shards into one working tree.

Each shard job runs f6_orchestrator.py on its own slice of a day's draw (STAR_VETTER_SHARD=i/K) in a
fresh checkout and hands back a tarball of the files that carry results. This script unpacks them
and unions the result tables by TIC, keeping every row already in the tree and adding rows for new
TICs only (so re-running a merge, or merging a shard twice, changes nothing).

What is merged:
  * the per-star result CSVs (manifest, vetting, novelty, blend, pixel);
  * new files under data/processed/sample_history/ (the record of which stars were drawn, so
    tomorrow's draw excludes them);
  * run records under data/runs/ (renamed with the shard so two shards cannot overwrite each other).
What is deliberately NOT merged: trained models and ML training sets (they are retrained from the merged
CSVs, never from a slice), dossier PDFs and site exports (regenerated after the merge).

Usage:  python merge_shards.py <root> <shards_dir> [--summary summary.md]
        <shards_dir> holds one directory (or .tgz) per shard.
Prints a JSON summary and writes a markdown summary for a pull request body.
"""

import io
import sys
import json
import shutil
import tarfile
from pathlib import Path

import pandas as pd

CSV_FILES = [
    "data/processed/f2c_manifest.csv",
    "data/processed/f3i_vetting_results.csv",
    "data/processed/f4f_novelty_results.csv",
    "data/processed/diag_blend_results.csv",
    "data/processed/diag_blend_neighbours.csv",
    "data/processed/diag_pixel_results_v2.csv",
    "data/processed/f4b_asassn_cache.csv",
]
KEY = "TIC"


def union_by_tic(base, others):
    """Rows of `base` first, then rows of each other frame whose TIC is not yet present.
    Frames without a TIC column are concatenated and exact duplicates dropped."""
    frames = [f for f in [base] + list(others) if f is not None and len(f.columns)]
    if not frames:
        return None
    if KEY not in frames[0].columns:
        out = pd.concat(frames, ignore_index=True)
        return out.drop_duplicates(keep="first").reset_index(drop=True)
    out = frames[0]
    for f in frames[1:]:
        if KEY not in f.columns:
            continue
        # the pixel table carries a control and a candidate row per TIC, so uniqueness is by TIC and role
        keys = [KEY] + (["role"] if "role" in out.columns and "role" in f.columns else [])
        have = set(map(tuple, out[keys].astype(str).values.tolist()))
        new = f[[tuple(r) not in have for r in f[keys].astype(str).values.tolist()]]
        out = pd.concat([out, new], ignore_index=True)
    return out


def unpack(shards_dir, scratch):
    """Each shard may be a directory or a .tgz; returns the list of directories to read from."""
    shards_dir, scratch = Path(shards_dir), Path(scratch)
    dirs = []
    for p in sorted(shards_dir.iterdir()):
        if p.is_dir():
            dirs.append(p)
        elif p.name.endswith((".tgz", ".tar.gz")):
            d = scratch / p.name.split(".")[0]
            d.mkdir(parents=True, exist_ok=True)
            with tarfile.open(p) as tf:
                for m in tf.getmembers():
                    if m.name.startswith("/") or ".." in Path(m.name).parts:
                        raise ValueError("unsafe path in shard archive: %s" % m.name)
                tf.extractall(d, filter="data")
            dirs.append(d)
    return dirs


def read_csv(path):
    return pd.read_csv(path) if Path(path).exists() else None


def funnel(proc):
    """The same cumulative counts f6_orchestrator.snapshot_cumulative reports."""
    manifest = read_csv(proc / "f2c_manifest.csv")
    vet = read_csv(proc / "f3i_vetting_results.csv")
    nov = read_csv(proc / "f4f_novelty_results.csv")
    pix = read_csv(proc / "diag_pixel_results_v2.csv")
    out = {"sampled": 0, "usable_light_curves": 0, "statistically_passing": 0, "novel": 0, "pixel_checked": 0, "on_target": 0}
    if manifest is not None:
        out["sampled"] = int(len(manifest))
        out["usable_light_curves"] = int((manifest["status"] == "OK").sum())
    if vet is not None and "status" in vet.columns and "depth_flagged_implausible" in vet.columns:
        out["statistically_passing"] = int(((vet["status"] == "OK") & (vet["depth_flagged_implausible"] == False)).sum())  # noqa: E712
    if nov is not None and "verdict" in nov.columns:
        out["novel"] = int((nov["verdict"] == "NOVEL").sum())
    if pix is not None and "role" in pix.columns:
        cand = pix[pix["role"] == "candidate"]
        out["pixel_checked"] = int(len(cand))
        out["on_target"] = int((cand["verdict"] == "ON_TARGET").sum())
    return out


def merge(root, shard_dirs):
    root = Path(root)
    before = funnel(root / "data" / "processed")
    added = {}
    for rel in CSV_FILES:
        path = root / rel
        base = read_csv(path)
        others = [read_csv(d / rel) for d in shard_dirs]
        others = [o for o in others if o is not None]
        if not others:
            continue
        merged = union_by_tic(base, others)
        n_before = 0 if base is None else len(base)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        added[rel] = int(len(merged) - n_before)
    hist = root / "data" / "processed" / "sample_history"
    hist.mkdir(parents=True, exist_ok=True)
    n_hist = 0
    for d in shard_dirs:
        for f in sorted((d / "data" / "processed" / "sample_history").glob("*.csv")):
            if not (hist / f.name).exists():
                shutil.copyfile(f, hist / f.name)
                n_hist += 1
    runs = root / "data" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    for d in shard_dirs:
        for f in sorted((d / "data" / "runs").glob("*.json")):
            dest = runs / ("%s_%s" % (d.name, f.name))
            if not dest.exists():
                shutil.copyfile(f, dest)
    after = funnel(root / "data" / "processed")
    per_shard = []
    for d in shard_dirs:
        m = read_csv(d / "data" / "processed" / "f2c_manifest.csv")
        per_shard.append({"shard": d.name, "manifest_rows": 0 if m is None else int(len(m))})
    return {"before": before, "after": after, "added_rows": added, "new_sample_history_files": n_hist,
            "shards": per_shard}


def render(summary, tests=None, extra=None):
    b, a = summary["before"], summary["after"]
    rows = [("Targets sampled", "sampled"), ("Usable light curves", "usable_light_curves"),
            ("Passing the statistical gates", "statistically_passing"), ("Novel after catalog cross-match", "novel"),
            ("Pixel-checked", "pixel_checked"), ("Confirmed on target", "on_target")]
    L = ["## Daily scaled pipeline run", "",
         "| Stage | Before | After | Added |", "|---|---|---|---|"]
    for label, k in rows:
        L.append("| %s | %d | %d | %+d |" % (label, b[k], a[k], a[k] - b[k]))
    L += ["", "Shards merged: %d. New sample-history files: %d." % (len(summary["shards"]), summary["new_sample_history_files"])]
    if tests:
        L += ["", "Tests: " + tests]
    if extra:
        L += ["", extra]
    L += ["", "These stars are an extension of the sample, drawn after the audit sample and pre-registration were frozen. "
          "Merging this pull request changes the audit numbers; run `py check_publication_readiness.py .` and regenerate "
          "the note afterwards.", ""]
    return "\n".join(L)


def main():
    args = sys.argv[1:]
    root, shards = Path(args[0]).resolve(), Path(args[1]).resolve()
    scratch = root / "data" / "_shard_unpack"
    dirs = unpack(shards, scratch)
    if not dirs:
        print("No shard results found in %s" % shards)
        sys.exit(1)
    summary = merge(root, dirs)
    shutil.rmtree(scratch, ignore_errors=True)
    print(json.dumps(summary, indent=1))
    if "--summary" in args:
        Path(args[args.index("--summary") + 1]).write_text(render(summary), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
