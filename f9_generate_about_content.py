"""
f9_generate_about_content.py

Generates the About page's project narrative and FAQ list once, using the
Claude API, grounded strictly in the pipeline's own already-computed numbers
(never invented). This is intentionally a single one-time batch call, not
per-visitor: the result is cached to data/processed/f9_about_content.json
and mirrored straight into site/public/data/about_content.json for the site
to read as a static file.

Cost control: if the cache file already exists, no API call is made at all.
Delete data/processed/f9_about_content.json (or pass --force) to regenerate,
for example after a big new run changes the pipeline's headline numbers.

v2: hardened PROMPT_TEMPLATE with an explicit hard-rules list. The original
prompt had no guard against overclaiming, and its first real output made
several false statements (manual/visual pixel check that is actually
automated, ML described as gating candidates when it is a second opinion,
"no caveats" claims, "joined the scientific literature" claims, stellar
masses this pipeline cannot measure, and the odd/even alias test mislabeled
as "period fitting"). Those were hand-corrected once via patch_about_content.py,
but this script's own prompt was never fixed - so a future --force run could
reproduce the same class of bugs. This version closes that gap the same way
f8_generate_writeups.py and f10_generate_discoveries.py were hardened.

v3: two changes.
1. The cached output now also stores n_confirmed_at_generation, the
   confirmed count that was live at generation time. check_about_content_drift.py
   reads that field to decide whether an automated run needs to pass --force
   here; the pipeline calls check_about_content_drift.py --auto-fix instead
   of calling this script directly, so --force only fires when the count
   moved.
2. A real --force run produced a narrative and an FAQ answer both claiming
   the ML score helps "other researchers" prioritize "future work" or
   "follow-up work" - nothing in the facts given to the prompt supports
   that claim, and it edges against the existing rule that nothing uses the
   ML score to prioritize or gate anything. Added an explicit rule against
   this invented framing so a regeneration does not reproduce it.

Requires:
  ANTHROPIC_API_KEY environment variable
  pip install anthropic (already installed if you ran f8_generate_writeups.py)

Usage:
  py f9_generate_about_content.py <project_root> [--force]
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
MAX_TOKENS = 1400

PROMPT_TEMPLATE = """You are writing content for the About page of a public science website called Star Vetter, which automatically vets candidate eclipsing binary stars found in TESS satellite data. Use ONLY the facts given below - do not invent, estimate, or add any number, fact, or claim that is not explicitly stated here or common, uncontroversial background knowledge about how eclipsing binaries and transit surveys work in general (never invent a number that looks like it came from this specific project). Plain, accurate, engaging language, aimed at a curious non-expert.

Project facts:
{facts_block}

HARD RULES (follow all of these - the previous version of this page broke every one of them and had to be hand-corrected):
- Do not use the words "discovery", "discovered", "genuine", "verified", "published", "literature", "peer-reviewed", or "proven" anywhere. "Confirmed" may only be used as this project's own defined term for "passed the pixel-level check" - always distinct from being scientifically verified.
- The pixel-level check is fully automated. Never describe it as manual, visual, or done by a human.
- The machine learning score is a second opinion only. Never say it decides, prioritizes, filters, screens, or gates which candidates get checked - nothing currently uses it to make that decision.
- Never describe the ML score as being used by other researchers, or as guiding, prioritizing, or informing anyone's future work or follow-up. The facts given state only its training size and how it compares to the baseline - nothing about who uses it or how, so do not invent a downstream use for it.
- Never claim all candidates are free of caveats or that the process has no open questions. Some candidates carry open caveats on their individual pages; the narrative and FAQs must leave room for that rather than imply universal cleanliness.
- Never say a candidate has joined the scientific literature, been added to an official catalog, or received professional or human follow-up. Being listed on this site is the end of what this pipeline itself does.
- This pipeline measures orbital period and relative eclipse depths from the light curve only. Never say it measures, derives, or determines stellar masses - that would require radial-velocity spectroscopy this project does not perform.
- Describe the period-alias check accurately if you mention it at all: it compares the depth of odd-numbered eclipses against even-numbered eclipses (an odd/even eclipse-depth test). Never call this"period fitting" or describe it as a period-search technique.
- Use only standard ASCII characters - no em dashes, no smart quotes (use a hyphen or comma instead, and straight quotes only).

Return ONLY valid JSON (no markdown code fences, no commentary before or after), matching exactly this shape:
{{
  "narrative": "a single paragraph, 150-220 words, explaining what this project does, how it works at a high level, and why the results are trustworthy",
  "faqs": [
    {{"question": "...", "answer": "..."}},
    ... 7 total FAQ entries covering: what an eclipsing binary is, what 'candidate' vs 'confirmed' means here, what the ML screening score is and is not, how a discovery gets checked (pixel-level check), what happens if the period looks aliased, whether a visitor can verify a result themselves, and what happens to a candidate after this site lists it
  ]
}}"""


def build_facts_block(index, model_metrics, pipeline_stats):
    lines = []
    gs = index.get("generated_stats", {})
    if gs.get("n_confirmed") is not None:
        lines.append(f"- Confirmed candidates listed on the site: {gs['n_confirmed']}")
    if gs.get("n_pixel_checked") is not None:
        lines.append(f"- Of those, pixel-level checked: {gs['n_pixel_checked']}")

    if model_metrics:
        b = model_metrics.get("baseline", {})
        lines.append(f"- Rule-based baseline: {b.get('description', 'n/a')}, "
                      f"recall {b.get('recall')}, precision {b.get('precision')}")
        lines.append(f"- ML model in use: {model_metrics.get('chosen_model', 'n/a')}, "
                      f"trained on {model_metrics.get('n_training_samples', 'n/a')} labeled examples, "
                      f"{'beats' if model_metrics.get('beats_baseline') else 'does not beat'} the rule baseline")

    if pipeline_stats:
        funnel = pipeline_stats.get("funnel") or []
        if funnel:
            steps = "; ".join(f"{s['label']}: {s['count']}" for s in funnel)
            lines.append(f"- Vetting funnel counts: {steps}")
        catalogs = pipeline_stats.get("catalogs") or []
        if catalogs:
            lines.append(f"- Candidates are cross-checked against {len(catalogs)} known variable-star catalogs: "
                         f"{', '.join(catalogs)}")
        cp = pipeline_stats.get("catalog_progress")
        if cp:
            lines.append(f"- Sky coverage so far: {cp.get('sampled_to_date')} of "
                         f"{cp.get('total_catalog')} targets sampled ({cp.get('fraction', 0) * 100:.1f}%)")

    return "\n".join(lines) if lines else "- (no additional pipeline statistics available this run)"


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
        print("Usage: py f9_generate_about_content.py <project_root> [--force]")
        sys.exit(1)
    root = Path(args[0]).resolve()
    site_data = root / "site" / "public" / "data"
    cache_path = root / "data" / "processed" / "f9_about_content.json"
    site_out_path = site_data / "about_content.json"

    if cache_path.exists() and not force:
        print(f"{cache_path.name} already exists - skipping the API call (no cost).")
        print("Pass --force, or delete that file, to regenerate.")
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        site_out_path.write_text(json.dumps(cached, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
        print(f"Re-copied cached content to {site_out_path}")
        return

    index = json.loads((site_data / "index.json").read_text(encoding="utf-8"))

    model_metrics = None
    mm_path = site_data / "model_metrics.json"
    if mm_path.exists():
        model_metrics = json.loads(mm_path.read_text(encoding="utf-8"))

    pipeline_stats = None
    ps_path = site_data / "pipeline_stats.json"
    if ps_path.exists():
        pipeline_stats = json.loads(ps_path.read_text(encoding="utf-8"))

    facts_block = build_facts_block(index, model_metrics, pipeline_stats)
    prompt = PROMPT_TEMPLATE.format(facts_block=facts_block)

    print("Calling Claude API once to generate the About page narrative and FAQs...")
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    try:
        content = extract_json(text)
    except json.JSONDecodeError as exc:
        print("ERROR: the model's reply was not valid JSON. Raw reply below - nothing was written.")
        print(text)
        raise SystemExit(1) from exc

    if "narrative" not in content or "faqs" not in content:
        print("ERROR: the model's reply was missing 'narrative' or 'faqs'. Raw reply below - nothing was written.")
        print(text)
        sys.exit(1)

    out = {
        "narrative": content["narrative"],
        "faqs": content["faqs"],
        "model": MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_confirmed_at_generation": index.get("generated_stats", {}).get("n_confirmed"),
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, indent=2, ensure_ascii=True, sort_keys=True), encoding="utf-8", newline="\n")
    site_out_path.write_text(json.dumps(out, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n")
    print(f"Generated narrative ({len(out['narrative'])} chars) and {len(out['faqs'])} FAQ(s).")
    print(f"Wrote {cache_path}")
    print(f"Wrote {site_out_path}")


if __name__ == "__main__":
    main()