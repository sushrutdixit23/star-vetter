"""
f10_generate_discoveries.py

Picks a handful of standout candidates by real, objective criteria already
computed by the pipeline (deepest eclipse, highest ML score, longest/
shortest period, clearest secondary eclipse), one candidate per category,
then calls the Claude API ONCE for all of them together to write a short
"why this stands out" paragraph per pick - grounded strictly in that
candidate's own numbers, never invented.

Only CLEAN-tier candidates are eligible picks: a candidate with any open
caveat should never be framed as a standout, since there is nothing to
reconcile a write-up against if the pipeline itself has already flagged a
doubt about it.

Cost control: this is a one-time batch call, not per-visitor. If
data/processed/f10_discoveries.json already exists, no API call is made at
all. Delete that file (or pass --force) to re-pick and regenerate, for
example after a run adds a lot of new confirmed candidates that might
unseat the current picks.

Requires:
  ANTHROPIC_API_KEY environment variable
  pip install anthropic (already installed if you ran the earlier f8/f9 scripts)

Usage:
  py f10_generate_discoveries.py <project_root> [--force]
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: the 'anthropic' package is not installed.")
    print("Install it with:")
    print("  py -m pip install anthropic")
    sys.exit(2)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1600


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

PROMPT_TEMPLATE = """You are writing short showcase blurbs for a "Standouts" page on Star Vetter, a public science website that automatically vets candidate eclipsing binary stars found in TESS satellite data. For each candidate below, write a headline (5-8 words) and a blurb (60-90 words) explaining why THIS candidate is a standout example of its named category. Use ONLY the facts given for that candidate - do not invent, estimate, or add any number, fact, or claim not explicitly stated.

Hard rules:
- Do not use the words "discovery", "genuine", "confirmed", "confirms", "follow-up", "ground-based", or "astronomers".
- Do not claim or imply any verification beyond what the facts state. This pipeline uses only automated TESS photometry and pixel-level image analysis - nothing else, no other telescopes, no human review.
- Call it a "candidate", never a confirmed discovery or a confirmed eclipsing binary.
- Use only standard ASCII characters - no em dashes, no smart quotes (use a hyphen or comma instead, straight quotes only).
- Plain, accurate, engaging language for a curious non-expert. Avoid the word "exciting".

Candidates:
{candidates_block}

Return ONLY valid JSON (no markdown code fences, no commentary), a JSON array with one object per candidate above, in the same order, matching exactly this shape:
[
  {{"tic": <tic number>, "headline": "...", "blurb": "..."}},
  ...
]"""


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


def facts_for_prompt(label, stat_text, rec):
    lines = [
        f"TIC {rec['tic']} - category: {label}",
        f"- Headline stat for this category: {stat_text}",
        f"- Orbital period: {rec['period_days']:.4f} days",
    ]
    if rec["primary_depth"] is not None:
        lines.append(f"- Primary eclipse depth: {rec['primary_depth'] * 100:.2f}%")
    else:
        lines.append("- Primary eclipse depth: not available")
    lines.append(f"- Detection significance (BLS signal-to-noise): {rec['bls_snr']:.1f}")
    if rec["ml_score"] is not None:
        lines.append(f"- ML screening score: {rec['ml_score']:.3f} (0 to 1)")
    lines.append(f"- Catalog check: matched in {rec['catalog_matches']} of {rec['n_catalogs']} known variable-star catalogs")
    if rec["secondary_sigma"] is not None:
        lines.append(f"- Secondary eclipse: detected at {rec['secondary_sigma']:.1f} sigma, phase {rec['secondary_phase']:.2f}")
    lines.append("- Vetting tier: CLEAN (no open caveats on this candidate)")
    return "\n".join(lines)


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return json.loads(text)


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
        print(f"{cache_path.name} already exists - skipping selection and the API call (no cost).")
        print("Pass --force, or delete that file, to re-pick and regenerate.")
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        site_out_path.write_text(json.dumps(cached, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
        print(f"Re-copied cached content to {site_out_path}")
        return

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))
    tics = [int(c["tic"]) for c in index["candidates"]]

    records = {}
    skipped_non_clean = 0
    for tic in tics:
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
            "facts": facts_for_prompt(label, stat_text, rec),
        })
        print(f"  {label}: TIC {best_tic} ({stat_text})")

    if not picks:
        print("No categories could be filled - nothing to generate.")
        return

    candidates_block = "\n\n".join(p["facts"] for p in picks)
    prompt = PROMPT_TEMPLATE.format(candidates_block=candidates_block)

    print(f"Calling Claude API once to write {len(picks)} standout blurb(s)...")
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    try:
        written = extract_json(text)
    except json.JSONDecodeError as exc:
        print("ERROR: the model's reply was not valid JSON. Raw reply below - nothing was written.")
        print(text)
        raise SystemExit(1) from exc

    written_by_tic = {int(w["tic"]): w for w in written if "tic" in w}

    discoveries = []
    for p in picks:
        w = written_by_tic.get(p["tic"])
        if not w:
            print(f"  WARNING: no written blurb came back for TIC {p['tic']} - skipped")
            continue
        discoveries.append({
            "tic": p["tic"],
            "category": p["category"],
            "category_label": p["category_label"],
            "stat_text": p["stat_text"],
            "headline": w.get("headline", ""),
            "blurb": w.get("blurb", ""),
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