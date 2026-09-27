"""
f8_generate_writeups.py

Calls the Claude API once per confirmed candidate to generate a short,
plain-English paragraph explaining what was found and why it matters -
grounded strictly in this candidate's own already-computed numbers, never
inventing anything.

Cost control: results are cached in data/processed/f8_writeups.json, keyed
by TIC. A candidate that already has a cached write-up is never sent to the
API again, so a routine pipeline run (including the 6-hourly CI cron) only
pays for candidates that are new since the last run.

Requires:
  ANTHROPIC_API_KEY environment variable
  pip install anthropic

Usage:
  py f8_generate_writeups.py <project_root>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    import anthropic
except ImportError:
    print("ERROR: the 'anthropic' package is not installed.")
    print("Install it with:")
    print("  py -m pip install anthropic")
    sys.exit(2)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 220

PROMPT_TEMPLATE = """You are writing one short paragraph (80-120 words) for a public science website, explaining a candidate eclipsing binary star to a curious non-expert reader. Use ONLY the facts given below - do not invent, estimate, or add any number, fact, or claim that is not explicitly stated here.

Hard rules:
- Do not use the words "discovery", "genuine", "confirmed", "confirms", "follow-up", "ground-based", or "astronomers".
- Do not claim or imply any verification beyond what the facts state. This pipeline uses only automated TESS photometry and pixel-level image analysis - nothing else, no other telescopes, no human review.
- Call it a "candidate", never a confirmed discovery or a confirmed eclipsing binary.
- If "Data quality flags" below lists anything, your paragraph MUST mention that open question in plain words, and must not describe the result as clean, genuine, or settled.
- Do not use the word "exciting" or "amazing". Use only standard ASCII characters - no em dashes, no smart quotes (use a hyphen or comma instead, and straight quotes only).
- Plain, accurate, engaging language. No headings, no bullet points, just the paragraph.

Facts about TIC {tic}:
- Orbital period: {period_days:.4f} days
- Primary eclipse depth: {depth_pct:.2f}% dimming
- Secondary eclipse: {secondary_text}
- Detection significance (BLS signal-to-noise): {bls_snr:.1f}
- Pixel-level confirmation: {pixel_text}
- Catalog novelty: {novelty_text}
{ml_line}- Data quality flags: {flags_text}

Write the paragraph now."""

def build_prompt(tic, cand, ml_score):
    eph = cand["ephemeris"]
    gates = cand["gates"]
    novelty = cand["novelty"]
    pixel = cand["pixel_check"]

    if gates.get("secondary_detected"):
        sig = gates.get("secondary_sigma") or 0.0
        phase = gates.get("secondary_phase") or 0.0
        secondary_text = f"detected at {sig:.1f} sigma, phase {phase:.2f}"
    else:
        secondary_text = "not detected"

    pixel_text = (f"difference-imaging peak signal-to-noise {pixel['diff_peak_snr']:.1f}, "
                  f"centroid offset {pixel['centroid_offset_arcsec']:.1f} arcsec from the target")

    matched = [c["name"] for c in novelty["catalogs"] if c["matched"]]
    if matched:
        novelty_text = f"already listed in: {', '.join(matched)}"
    else:
        novelty_text = (f"not found in any of the {len(novelty['catalogs'])} variable-star "
                         f"catalogs checked - a genuinely novel find")

    if ml_score is not None:
        ml_line = (f"- ML screening score: {ml_score:.2f} (0 to 1, higher means the "
                    f"pipeline's model finds this more likely to be a real target star)\n")
    else:
        ml_line = ""

    flags = [c["text"] for c in cand.get("caveats", []) if c.get("tier") != "CLEAN"]
    flags_text = "; ".join(flags) if flags else "none - this candidate passed every check cleanly"

    return PROMPT_TEMPLATE.format(
        tic=tic, period_days=eph["period_days"], depth_pct=eph["depth_frac"] * 100,
        secondary_text=secondary_text, bls_snr=eph["bls_snr"], pixel_text=pixel_text,
        novelty_text=novelty_text, ml_line=ml_line, flags_text=flags_text,
    )

def main():
    if len(sys.argv) != 2:
        print("Usage: py f8_generate_writeups.py <project_root>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    site_data = root / "site" / "public" / "data"
    cand_dir = site_data / "candidates"
    out_path = root / "data" / "processed" / "f8_writeups.json"

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))
    tics = [int(c["tic"]) for c in index["candidates"]]

    cache = {}
    if out_path.exists():
        cache = json.loads(out_path.read_text(encoding="utf-8"))

    ml_scores = {}
    scores_path = root / "data" / "processed" / "f7_scores.csv"
    if scores_path.exists():
        sdf = pd.read_csv(scores_path)
        for _, r in sdf.iterrows():
            if pd.notna(r.get("ml_score")):
                ml_scores[int(r["TIC"])] = float(r["ml_score"])

    todo = [t for t in tics if str(t) not in cache]
    print(f"{len(tics)} confirmed candidate(s), {len(cache)} already have a cached write-up, "
          f"{len(todo)} need one generated.")
    if not todo:
        print("Nothing to do.")
        return

    client = anthropic.Anthropic()
    done = 0
    for tic in todo:
        cand_path = cand_dir / f"TIC{tic}.json"
        if not cand_path.exists():
            print(f"  WARNING: TIC {tic} has no candidate JSON - skipped")
            continue
        cand = json.loads(cand_path.read_text(encoding="utf-8"))
        prompt = build_prompt(tic, cand, ml_scores.get(tic))
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as exc:
            print(f"  WARNING: TIC {tic} generation failed ({repr(exc)[:150]}) - will retry next run")
            continue
        cache[str(tic)] = {
            "writeup": text,
            "model": MODEL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        done += 1
        print(f"  TIC {tic}: generated ({len(text)} chars)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cache, indent=2, ensure_ascii=True, sort_keys=True),
                         encoding="utf-8", newline="\n")
    print(f"Generated {done} new write-up(s). Wrote {out_path}")

if __name__ == "__main__":
    main()