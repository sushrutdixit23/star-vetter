// A last line of defence for the AI-written plain-English text. The real
// check belongs in the pipeline (f8_generate_writeups.py); this refuses to
// display any text that uses discovery / certainty language, or that names
// a different star than the page it is on. It deliberately errs on the side
// of hiding: an honest paragraph hidden by mistake costs little, a false one
// shown costs the site's credibility.
const BLOCKED = [
  "discover",
  "genuine",
  "astronomer",
  "previously unknown",
  "escaped detection",
  "our catalog",
  "catalog of known",
  "high confidence",
  "highly likely",
  "real astronomical",
  "independent methods",
  "independent checks confirm",
  "new find",
  "ground-based",
  "follow-up observations confirmed",
];

export function safeWriteup(text: string | null | undefined, tic?: number): string | null {
  if (!text) return null;
  const t = text.trim();
  if (t.length === 0) return null;
  const lower = t.toLowerCase();
  for (const stem of BLOCKED) {
    if (lower.includes(stem)) return null;
  }
  if (tic !== undefined) {
    const mentioned = t.match(/TIC ?[0-9]+/g) ?? [];
    for (const m of mentioned) {
      if (m.replace(/[^0-9]/g, "") !== String(tic)) return null;
    }
  }
  return t;
}
