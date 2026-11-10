import re
import sys
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import draft_rnaas as dr

# Programmatic gate for "is the ANALYSIS ready for the publication phase".
#
# It separates two things:
#   * ANALYSIS checks: everything the pipeline can settle by itself. All must pass.
#   * AUTHOR actions: things only the author can do (accounts, identity, legal
#     confirmations, a registry deposit). These never pass automatically; they are listed.
#
# Exit code 0 only when every analysis check passes. Prints READY or NOT READY with reasons.

DATA = Path("site") / "public" / "data"
YEAR9_START = datetime(2026, 11, 26, tzinfo=timezone.utc)
JD_YEAR9_START = 2440587.5 + YEAR9_START.timestamp() / 86400.0
OVERCLAIM = ["new binary stars", "newly discovered", "we discovered", "genuine discovery", "new discoveries", "confirmed binaries",
             "novel binar", "first-ever", "breakthrough"]


def _json(root, name):
    p = root / DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _text_files(root):
    out = [root / "docs" / "rnaas_note.md"]
    for p in (root / "site" / "src" / "app").rglob("*.tsx"):
        out.append(p)
    return [p for p in out if p.exists()]


def analysis_checks(root, now=None):
    now = now or datetime.now(timezone.utc)
    res = []

    def add(name, ok, detail):
        res.append({"check": name, "ok": bool(ok), "detail": detail})

    dash = _json(root, "dashboard.json")
    n_stars = len(dash["sky"]) if dash else 0
    zdir = root / "data" / "processed" / "f17_ztf"
    n_ztf = len(list(zdir.glob("TIC*.json"))) if zdir.exists() else 0
    add("ZTF scan run for every survivor", n_stars > 0 and n_ztf >= n_stars, "%d of %d stars have a ZTF result file" % (n_ztf, n_stars))

    ztf = _json(root, "ztf_independent.json")
    ev = _json(root, "evidence.json")
    add("ztf_independent.json covers every survivor", bool(ztf) and ztf["summary"]["stars"] >= n_stars,
        "%s stars exported" % (ztf["summary"]["stars"] if ztf else "no file"))
    add("evidence.json covers every survivor", bool(ev) and ev["summary"]["stars"] == n_stars,
        "%s stars" % (ev["summary"]["stars"] if ev else "no file"))
    if ev and ztf:
        add("evidence.json agrees with the ZTF export (no stale tier)",
            sum(v for k, v in ev["summary"]["by_ztf_status"].items() if k != "NOT_RUN") == ztf["summary"]["stars"] and
            ev["summary"]["by_ztf_status"].get("NOT_RUN", 0) == n_stars - ztf["summary"]["stars"],
            "evidence ZTF statuses %s vs %d exported" % (ev["summary"]["by_ztf_status"], ztf["summary"]["stars"]))

    for name in ("gaia_dr3.json", "prior_art.json", "gaia_dr4_plan.json", "recovery.json", "recovery_min2.json", "recovery_hostsnr48.6.json"):
        add("%s present" % name, (root / DATA / name).exists(), "")

    note_p = root / "docs" / "rnaas_note.md"
    if note_p.exists():
        txt = note_p.read_text(encoding="utf-8")
        words, tables = dr.word_count(txt), dr.table_count(txt)
        add("RNAAS note within limits", words <= dr.WORD_LIMIT and tables == 1, "%d words (limit %d), %d table(s)" % (words, dr.WORD_LIMIT, tables))
        try:
            extra = {k: _json(root, f) for k, f in (("ev", "evidence.json"), ("ztf", "ztf_independent.json"), ("gdr3", "gaia_dr3.json"),
                                                    ("prior", "prior_art.json"), ("rec2", "recovery_min2.json"))}
            fresh = dr.render(_json(root, "audit.json"), _json(root, "recovery.json"), _json(root, "atlas_alias.json"), _json(root, "neighbours.json"),
                              _json(root, "predictions.json"), _json(root, "novelty_extra.json"), _json(root, "tess_catalog_xmatch.json"), **extra)
            add("RNAAS note matches the data files (not stale)", fresh.strip() == txt.strip(), "regenerated text %s the committed note" % ("equals" if fresh.strip() == txt.strip() else "DIFFERS from"))
        except (TypeError, KeyError) as e:  # missing input
            add("RNAAS note matches the data files (not stale)", False, "could not regenerate: %r" % e)
    else:
        add("RNAAS note exists", False, "docs/rnaas_note.md missing")

    pred = _json(root, "predictions.json")
    if pred:
        rule = json.dumps(pred).lower()
        add("grading rule includes the QLP timing term", "3-minute" in rule or "3 minute" in rule or "3 min" in rule, "")
        first = min((p["t_btjd"] for s in pred["stars"] for p in s["predictions"]), default=None)
        add("every prediction lies after the Year 9 start", first is not None and first + 2457000.0 > JD_YEAR9_START, "first predicted minimum BJD %s" % (round(first + 2457000.0, 3) if first is not None else "none"))
    else:
        add("predictions.json present", False, "")

    bad = []
    for p in _text_files(root):
        low = p.read_text(encoding="utf-8").lower()
        for ph in OVERCLAIM:
            if ph in low:
                bad.append("%s: '%s'" % (p.relative_to(root), ph))
    add("no overclaiming phrases in the note or site pages", not bad, "; ".join(bad) if bad else "scanned %d files for %d phrases" % (len(_text_files(root)), len(OVERCLAIM)))

    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=30).stdout.strip()
        add("working tree committed", out == "", "%d uncommitted path(s)" % len(out.splitlines()) if out else "clean")
    except Exception as e:  # noqa: BLE001
        add("working tree committed", False, repr(e))
    return res


def author_actions(root, now=None):
    now = now or datetime.now(timezone.utc)
    days = (YEAR9_START - now).days
    frozen = list((root / "preregistration").glob("star-vetter-predictions-*.zip")) if (root / "preregistration").exists() else []
    items = []
    items.append(("Merge PR #1 then PR #2 on GitHub", None))
    items.append(("Freeze the predictions: py freeze_predictions.py . then py freeze_predictions.py --verify <bundle>; %s" %
                  ("a frozen bundle already exists" if frozen else "no frozen bundle yet; %d days before Year 9 starts (2026-11-26)" % days), bool(frozen)))
    items.append(("Upload the zip to Zenodo with your ORCID and send me the DOI", None))
    note = (root / "docs" / "rnaas_note.md").read_text(encoding="utf-8") if (root / "docs" / "rnaas_note.md").exists() else ""
    n = len(re.findall(r"\[\[.*?\]\]", note))
    items.append(("Fill the %d [[...]] fields in docs/rnaas_note.md (ORCID/affiliation, Zenodo DOI, repository URL, AI-usage confirmation)" % n, n == 0))
    items.append(("Final prior-art look in ADS for 2025-2026 papers on these TIC numbers (not reachable from the sandbox)", None))
    items.append(("Optional: ATLAS forced photometry for the southern stars needs your own ATLAS account/token", None))
    return items


def main():
    if len(sys.argv) < 2:
        print("Usage: py check_publication_readiness.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    res = analysis_checks(root)
    ok = all(r["ok"] for r in res)
    for r in res:
        print("[%s] %s%s" % ("PASS" if r["ok"] else "FAIL", r["check"], (" - " + r["detail"]) if r["detail"] else ""))
    print()
    print("ANALYSIS: %s" % ("READY" if ok else "NOT READY"))
    print("\nAUTHOR ACTIONS (only you can do these):")
    for text, done in author_actions(root):
        print("  [%s] %s" % ("x" if done else " ", text))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
