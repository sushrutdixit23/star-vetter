"""
f10_generate_discoveries.py

Picks a handful of standout candidates by real, objective criteria already
computed by the pipeline (deepest eclipse, highest ML score, longest/
shortest period, clearest secondary eclipse), one candidate per category,
and writes a short "why this stands out" paragraph for each.

The text is built from fixed templates filled with that candidate's own
numbers. No language model writes it: an earlier version did, and it produced
hype ("unprecedented", "high-confidence") and one wrong sentence (a depth of
7.88 percent described as "dimming to 7.88 percent of their combined light").
Templates cannot invent a claim, and every sentence is checked by
writeup_guard before it is written.

Only CLEAN-tier candidates are eligible picks.

Usage:
  py f10_generate_discoveries.py <project_root> [--force]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import writeup_guard

MODEL = "fixed templates (no language model)"


def score_deepest(rec):
    return rec["primary_depth"] if rec["primary_depth"] is not None else -1


def score_longest_period(rec):
    return rec["period_days"]


def score_shortest_period(rec):
    return -rec["period_days"]


def score_ml(rec):
    return rec["ml_score"] if rec["ml_score"] is not None else -1


def score_secondary(rec):
    return rec["secondary_sigma"] if rec["secondary_sigma"] is not None else -1


CATEGORIES = [
    ("deepest_eclipse", "Deepest eclipse", score_deepest,
     lambda r: f"{r['primary_depth'] * 100:.1f}% dimming"),
    ("longest_period", "Longest orbital period", score_longest_period,
     lambda r: f"{r['period_days']:.1f} day orbit"),
    ("shortest_period", "Shortest orbital period", score_shortest_period,
     lambda r: f"{r['period_days']:.3f} day orbit"),
    ("highest_ml_score", "Highest ML screening score", score_ml,
     lambda r: f"ML score {r['ml_score']:.3f}"),
    ("clearest_secondary", "Clearest secondary eclipse", score_secondary,
     lambda r: f"secondary eclipse at {r['secondary_sigma']:.1f} sigma"),
]

def build_record(tic, cand, detail):
    eph = cand["ephemeris"]
    gates = cand["gates"]
    novelty = cand["novelty"]
    secondary = detail.get("secondary") if detail else None
    return {
        "tic": tic,
        "period_days": detail["period_true_days"] if detail else eph["period_days"],
        "primary_depth": detail["primary"]["depth"] if detail and detail.get("primary") else eph["depth_frac"],
        "bls_snr": eph["bls_snr"],
        "ml_score": detail.get("ml_score") if detail else None,
        "catalog_matches": sum(1 for c in novelty["catalogs"] if c["matched"]),
        "n_catalogs": len(novelty["catalogs"]),
        "secondary_sigma": secondary["sigma"] if secondary and secondary.get("detected") else None,
        "secondary_phase": secondary["phase"] if secondary and secondary.get("detected") else None,
        "odd_even_z": gates["odd_even_z"],
    }


def _tail(rec):
    parts = []
    if rec["secondary_sigma"] is not None:
        parts.append(f"A secondary eclipse is also detected, at {rec['secondary_sigma']:.1f} sigma.")
    else:
        parts.append("No secondary eclipse was detected.")
    if rec["n_catalogs"]:
        if rec["catalog_matches"] == 0:
            parts.append(f"It matched none of the {rec['n_catalogs']} catalogs searched, which is weak evidence of novelty.")
        else:
            parts.append(f"It matched {rec['catalog_matches']} of {rec['n_catalogs']} catalogs searched.")
    parts.append("It is a candidate, not a confirmed eclipsing binary.")
    return " ".join(parts)


def write_text(key, rec):
    """Return (headline, blurb) for one pick, from its own numbers only."""
    d = rec["primary_depth"]
    depth = f"{d * 100:.2f}%" if d is not None else "an unmeasured amount"
    P = rec["period_days"]
    snr = rec["bls_snr"]
    bits = []
    if key != "longest_period" and key != "shortest_period":
        bits.append(f"orbital period {P:.4f} days")
    if key != "deepest_eclipse" and d is not None:
        bits.append(f"primary eclipse depth {depth}")
    bits.append(f"detection signal-to-noise {snr:.0f}")
    base = "Measured: " + ", ".join(bits) + "."
    if key == "deepest_eclipse":
        head = "Deepest eclipse among the clean candidates"
        lead = f"The primary eclipse removes {depth} of the light, the deepest of any candidate with no open caveats."
    elif key == "longest_period":
        head = "Longest orbit among the clean candidates"
        lead = f"The two stars take {P:.1f} days to orbit each other, the longest period of any candidate with no open caveats."
    elif key == "shortest_period":
        head = "Shortest orbit among the clean candidates"
        lead = f"The two stars take only {P:.3f} days to orbit each other, the shortest period of any candidate with no open caveats."
    elif key == "highest_ml_score":
        head = "Highest score from the screening model"
        lead = f"The screening model gives it {rec['ml_score']:.3f} out of 1, the highest of the clean candidates. The model is a second opinion and is not used to accept or reject anything."
    elif key == "clearest_secondary":
        head = "Clearest secondary eclipse"
        lead = f"Its secondary eclipse is detected at {rec['secondary_sigma']:.1f} sigma, the clearest of the clean candidates."
    else:
        head = "Standout candidate"
        lead = ""
    tail = _tail(rec)
    if key == "clearest_secondary":
        tail = tail.replace(f"A secondary eclipse is also detected, at {rec['secondary_sigma']:.1f} sigma. ", "")
    return head, " ".join(x for x in (lead, base, tail) if x)


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if len(args) != 1:
        print("Usage: py f10_generate_discoveries.py <project_root> [--force]")
        sys.exit(1)
    root = Path(args[0]).resolve()
    site_data = root / "site" / "public" / "data"
    cand_dir = site_data / "candidates"
    detail_dir = site_data / "detail"
    cache_path = root / "data" / "processed" / "f10_discoveries.json"
    site_out_path = site_data / "discoveries.json"

    if cache_path.exists() and not force:
        print(f"{cache_path.name} already exists - skipping re-selection.")
        print("Pass --force, or delete that file, to re-pick and regenerate.")
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        site_out_path.write_text(json.dumps(cached, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
        print(f"Re-copied cached content to {site_out_path}")
        return

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))
    tics = [int(c["tic"]) for c in index["candidates"]]

    # stars already listed in a catalog at the same period are never "standouts"
    known = set()
    ne_path = site_data / "novelty_extra.json"
    if ne_path.exists():
        ne = json.loads(ne_path.read_text(encoding="utf-8"))["stars"]
        known = {int(t) for t, v in ne.items() if v.get("verdict") == "ALREADY_KNOWN"}

    records = {}
    skipped_non_clean = 0
    for tic in tics:
        if tic in known:
            continue
        cand_path = cand_dir / f"TIC{tic}.json"
        if not cand_path.exists():
            continue
        cand = json.loads(cand_path.read_text(encoding="utf-8"))
        if cand.get("tier") != "CLEAN":
            skipped_non_clean += 1
            continue
        detail_path = detail_dir / f"TIC{tic}.json"
        detail = json.loads(detail_path.read_text(encoding="utf-8")) if detail_path.exists() else None
        records[tic] = build_record(tic, cand, detail)

    print(f"{len(records)} CLEAN-tier candidate(s) eligible ({skipped_non_clean} excluded for having open caveats).")

    if not records:
        print("No CLEAN-tier candidates found - nothing to pick from.")
        return

    used_tics = set()
    picks = []
    for key, label, score_fn, stat_fn in CATEGORIES:
        best_tic = None
        best_score = None
        for tic, rec in records.items():
            if tic in used_tics:
                continue
            s = score_fn(rec)
            if s is None:
                continue
            if best_score is None or s > best_score:
                best_score = s
                best_tic = tic
        if best_tic is None:
            print(f"  Skipping category '{label}' - no eligible candidate found.")
            continue
        used_tics.add(best_tic)
        rec = records[best_tic]
        stat_text = stat_fn(rec)
        picks.append({
            "tic": best_tic,
            "category": key,
            "category_label": label,
            "stat_text": stat_text,
        })
        print(f"  {label}: TIC {best_tic} ({stat_text})")

    if not picks:
        print("No categories could be filled - nothing to generate.")
        return

    discoveries = []
    for p in picks:
        head, blurb = write_text(p["category"], records[p["tic"]])
        if not (writeup_guard.is_safe(head, p["tic"]) and writeup_guard.is_safe(blurb, p["tic"])):
            print(f"  WARNING: template text for TIC {p['tic']} failed the language guard - skipped")
            continue
        discoveries.append({
            "tic": p["tic"],
            "category": p["category"],
            "category_label": p["category_label"],
            "stat_text": p["stat_text"],
            "headline": head,
            "blurb": blurb,
        })

    out = {
        "discoveries": discoveries,
        "model": MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, indent=2, ensure_ascii=True, sort_keys=True), encoding="utf-8", newline="\n")
    site_out_path.write_text(json.dumps(out, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
    print(f"Wrote {len(discoveries)} standouts to {cache_path}")
    print(f"Wrote {site_out_path}")


if __name__ == "__main__":
    main()