"""Freeze the eclipse predictions into a tamper-evident bundle for pre-registration.

A prediction only counts if it provably existed before the data it predicts.
This builds a folder (and a zip) holding the exact predictions, the evidence
behind their grades, the code that produced them, and a manifest of SHA-256
hashes. Deposit the zip on Zenodo (which gives it a DOI and a timestamp you
cannot edit afterwards). Anyone can later check the files against the manifest
with --verify.

What it refuses to do, so the bundle cannot quietly be wrong:
  * freeze an empty prediction list
  * freeze if any predicted eclipse is already in the past
  * freeze from a git tree with uncommitted changes (the code hash would not
    match any commit), unless --allow-dirty is given and recorded
It WARNS if TESS Year 9 has already begun (some predicted sectors may then
already be public, which weakens the pre-registration for those sectors).

Usage:
  python freeze_predictions.py <root> [--out DIR] [--allow-dirty]
  python freeze_predictions.py --verify <bundle-folder-or-zip>
Writes: <out or root/preregistration>/star-vetter-predictions-<YYYYMMDD>/ and .zip
Exit:   0 ok, 1 refused or verification failed
"""

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

YEAR9_START_UTC = "2026-11-26T00:00:00Z"      # TESS Sector 111 begins
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)         # so the zip bytes depend only on content

CODE_FILES = ["f13_ephemeris.py", "f14_novelty_extra.py", "f14_calibrate.py", "export_predictions.py",
              "validate_f13_prsa.py", "calibrate_f13_holdout.py", "freeze_predictions.py", "upstream.py"]
DATA_FILES = ["f13_ephemerides.csv", "f13_holdout.csv", "f13_predictions.csv", "f13_validation_prsa.csv",
              "f14_novelty_extra.csv", "f14_extra_catalogs.csv", "f14_recall_known_ebs.json"]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle_hash(files):
    """One hash for the whole bundle: sha256 of 'name<TAB>hash' lines, sorted by name."""
    lines = "".join(f"{name}\t{info['sha256']}\n" for name, info in sorted(files.items()))
    return sha256_bytes(lines.encode("ascii"))


def git_state(root):
    def run(*a):
        try:
            return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, timeout=20, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    commit = run("rev-parse", "HEAD")
    if commit is None:
        return {"commit": None, "dirty": None, "branch": None}
    dirty = bool(run("status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "dirty": dirty, "branch": run("rev-parse", "--abbrev-ref", "HEAD")}


def parse_utc(s):
    return datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def check_predictions(pred, now):
    """Return (problems, warnings) for a predictions.json payload."""
    problems, warnings = [], []
    stars = pred.get("stars") or []
    if not stars:
        problems.append("predictions.json lists no stars")
        return problems, warnings
    past = [(s["tic"], p["utc"]) for s in stars for p in s["predictions"] if parse_utc(p["utc"]) <= now]
    if past:
        problems.append(f"{len(past)} predicted eclipse(s) are already in the past, e.g. TIC {past[0][0]} at {past[0][1]}")
    if now >= parse_utc(YEAR9_START_UTC):
        warnings.append("TESS Year 9 has already begun: data for the earliest predicted sectors may be public.")
    return problems, warnings


def flat_table(pred):
    rows = []
    for s in pred["stars"]:
        for p in s["predictions"]:
            rows.append({"tic": s["tic"], "grade": s["grade"], "sector": p["sector"], "cycle": p["cycle"],
                         "t_btjd": p["t_btjd"], "utc": p["utc"], "sigma_min": p["sigma_min"],
                         "sector_dates_approximate": bool(p.get("approximate")),
                         "period_days": s["ephemeris"]["period_days"], "t0_btjd": s["ephemeris"]["t0_btjd"]})
    return pd.DataFrame(rows)


def readme(manifest, pred):
    c = pred["counts"]
    conv = pred["conventions"]
    return f"""STAR VETTER - TESS YEAR 9 ECLIPSE PREDICTIONS (PRE-REGISTRATION)

Frozen (UTC):  {manifest['frozen_utc']}
Bundle hash:   {manifest['bundle_sha256']}
Code commit:   {manifest['git']['commit']}
TESS Year 9 begins: {YEAR9_START_UTC} (Sector 111)

WHAT THIS IS
{c['listed']} candidate eclipsing binaries, each with a dated primary-eclipse prediction and a
1-sigma uncertainty, written down before the data exist. {c['listed_validated']} are graded VALIDATED
and {c['listed_unvalidated']} NOT VALIDATED (see GRADES). These are candidates, not confirmed
binaries, and this deposit makes no claim that any of them is new.

HOW EACH PREDICTION WILL BE GRADED (fixed now, applied later)
{conv['outcome_rule']}

GRADES
{conv['grades']}

TIME AND UNCERTAINTY
{conv['time_scale']}
{conv['sigma']}

WHICH STARS ARE LISTED (applied mechanically to {c['candidates_considered']} candidates)
""" + "\n".join(f"  {i + 1}. {r}" for i, r in enumerate(pred["selection_rule"])) + f"""

Stars left out, by reason: {json.dumps(pred['excluded'])}
Stars rejected by the hold-out test: {c['rejected_failed_holdout']}

FILES
  predictions.json / predictions.csv   the predictions (identical content)
  data/                                ephemerides, hold-out results, validation, catalog cross-match
  code/                                the exact scripts that produced them
  MANIFEST.json                        SHA-256 of every file and one hash for the bundle
  README.txt, .zenodo.json             descriptive only; not hashed (the README quotes the bundle hash)

CHECK IT
  python freeze_predictions.py --verify <this folder or the zip>
Then confirm the bundle hash above matches the one on the Zenodo record.

KNOWN LIMITS
  * Retrospective tests cannot rule out a period change after the last measured eclipse.
  * Sectors 117-121 have interpolated dates; the sector may shift by days.
  * A star absent from the catalogs searched is weak evidence of novelty.
"""


def build(root, out_dir, allow_dirty=False, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root).resolve()
    pj = root / "site" / "public" / "data" / "predictions.json"
    if not pj.exists():
        return 1, ["predictions.json not found; run export_predictions.py first"], None
    pred = json.loads(pj.read_text(encoding="utf-8"))
    problems, warnings = check_predictions(pred, now)
    git = git_state(root)
    if git["dirty"] and not allow_dirty:
        problems.append("git tree has uncommitted changes; commit first or pass --allow-dirty")
    if git["dirty"] and allow_dirty:
        warnings.append("frozen from a DIRTY git tree: the code hashes do not match any commit")
    if problems:
        return 1, problems + warnings, None

    stamp = now.strftime("%Y%m%d")
    bundle = Path(out_dir) / f"star-vetter-predictions-{stamp}"
    if bundle.exists():
        return 1, [f"{bundle} already exists; a frozen bundle is never overwritten"], None
    (bundle / "data").mkdir(parents=True)
    (bundle / "code").mkdir()

    contents = {"predictions.json": pj.read_bytes(),
                "predictions.csv": flat_table(pred).to_csv(index=False, lineterminator="\n").encode("utf-8")}
    for name in DATA_FILES:
        p = root / "data" / "processed" / name
        if p.exists():
            contents[f"data/{name}"] = p.read_bytes()
        else:
            warnings.append(f"missing data file {name}")
    for name in CODE_FILES:
        p = root / name
        if p.exists():
            contents[f"code/{name}"] = p.read_bytes()
    for name, data in contents.items():
        (bundle / name).write_bytes(data)

    files = {name: {"sha256": sha256_bytes(data), "bytes": len(data)} for name, data in contents.items()}
    manifest = {"frozen_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "year9_start_utc": YEAR9_START_UTC,
                "git": git, "counts": pred["counts"], "files": files}
    manifest["bundle_sha256"] = bundle_hash(files)
    (bundle / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    (bundle / "README.txt").write_text(readme(manifest, pred), encoding="ascii", errors="replace", newline="\n")
    (bundle / ".zenodo.json").write_text(json.dumps({
        "title": "Star Vetter: dated eclipse predictions for TESS Year 9 (pre-registration)",
        "upload_type": "dataset",
        "description": ("Dated primary-eclipse predictions for candidate eclipsing binaries, frozen before TESS Year 9 data are "
                        "public, with the grading rule, validation evidence and code. Bundle hash " + manifest["bundle_sha256"]),
        "creators": [{"name": "Dixit, Sushrut"}],
        "keywords": ["TESS", "eclipsing binaries", "pre-registration", "eclipse timing", "predictions"],
        "license": "cc-by-4.0",
        "access_right": "open",
    }, indent=1), encoding="utf-8", newline="\n")

    zpath = bundle.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bundle.rglob("*")):
            if p.is_file():
                zi = zipfile.ZipInfo(f"{bundle.name}/{p.relative_to(bundle).as_posix()}", FIXED_ZIP_TIME)
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, p.read_bytes())
    return 0, warnings, {"bundle": bundle, "zip": zpath, "manifest": manifest}


def verify(path):
    """Check every file against MANIFEST.json. Returns (ok, messages)."""
    path = Path(path)
    msgs = []
    if path.is_file() and path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith("MANIFEST.json")]
            if not names:
                return False, ["no MANIFEST.json in the zip"]
            prefix = names[0][: -len("MANIFEST.json")]
            manifest = json.loads(z.read(names[0]).decode("utf-8"))
            blobs = {n[len(prefix):]: z.read(n) for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")}
        read = blobs.get
    else:
        mp = path / "MANIFEST.json"
        if not mp.exists():
            return False, ["no MANIFEST.json in the folder"]
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        read = lambda n: (path / n).read_bytes() if (path / n).exists() else None  # noqa: E731
    ok = True
    for name, info in sorted(manifest["files"].items()):
        data = read(name)
        if data is None:
            ok = False
            msgs.append(f"MISSING  {name}")
        elif sha256_bytes(data) != info["sha256"]:
            ok = False
            msgs.append(f"CHANGED  {name}")
    if bundle_hash(manifest["files"]) != manifest.get("bundle_sha256"):
        ok = False
        msgs.append("bundle hash does not match the file list")
    if ok:
        msgs.append(f"all {len(manifest['files'])} files match; bundle hash {manifest['bundle_sha256']}")
    return ok, msgs


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--verify":
        if len(argv) < 2:
            print(__doc__)
            return 1
        ok, msgs = verify(argv[1])
        print("\n".join(msgs))
        return 0 if ok else 1
    root = Path(argv[0]).resolve()
    out = Path(root / "preregistration")
    for i, a in enumerate(argv):
        if a == "--out":
            out = Path(argv[i + 1])
    code, msgs, res = build(root, out, allow_dirty="--allow-dirty" in argv)
    for m in msgs:
        print(("REFUSED: " if code else "warning: ") + m)
    if res:
        print(f"Bundle: {res['bundle']}\nZip:    {res['zip']}\nBundle hash: {res['manifest']['bundle_sha256']}")
        print(f"{res['manifest']['counts']['listed']} stars frozen. Upload the zip to Zenodo, then publish the DOI.")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
