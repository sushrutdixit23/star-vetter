import type { ModelMetrics, PipelineStats } from "./types";

// Numbers in AI-written prose must never freeze. Two defences: tokens such
// as {confirmed} or {sampled} are filled from the live exports at render
// time, and any sentence that still quotes a count (10 or more, not a
// year, decimal or percentage) that is not a current live value - or that
// holds an unfilled token - is dropped rather than shown.

export interface LiveNumbers {
  tokens: Record<string, number>;
  allowed: Set<number>;
}

const FUNNEL_TOKENS = ["sampled", "usable", "passing", "novel", "pixel_checked", "confirmed"];

export function liveNumbers(stats: PipelineStats | null, metrics: ModelMetrics | null): LiveNumbers {
  const tokens: Record<string, number> = {};
  if (stats) {
    stats.funnel.slice(0, 6).forEach((s, i) => {
      tokens[FUNNEL_TOKENS[i]] = s.count;
    });
    tokens.catalogs = stats.catalogs.length;
    tokens.vetting_gates = stats.vetting_gates.length;
    tokens.pixel_gates = stats.pixel_gates.length;
  }
  if (metrics) {
    tokens.training_samples = metrics.n_training_samples;
    tokens.training_positive = metrics.n_training_positive;
    tokens.training_negative = metrics.n_training_negative;
    tokens.cv_folds = metrics.n_cv_folds;
  }
  return { tokens, allowed: new Set(Object.values(tokens)) };
}

export function fillTokens(text: string, tokens: Record<string, number>): string {
  return text.replace(/[{]([a-z_]+)[}]/g, (m: string, name: string) => (name in tokens ? tokens[name].toLocaleString("en-US") : m));
}

function splitSentences(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    cur += ch;
    if ((ch === "." || ch === "!" || ch === "?") && (i + 1 >= text.length || text[i + 1] === " ")) {
      if (cur.trim()) out.push(cur.trim());
      cur = "";
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

export function currentOnly(text: string | null, allowed: Set<number>): string | null {
  if (!text) return null;
  const kept = splitSentences(text).filter((s) => {
    if (s.includes("{")) return false;
    const nums = s.match(/[0-9][0-9,]*([.][0-9]+)?%?/g) ?? [];
    for (const n of nums) {
      if (n.includes(".") || n.endsWith("%")) continue;
      const v = parseInt(n.replace(/,/g, ""), 10);
      if (!Number.isFinite(v) || v < 10) continue;
      if (v >= 1900 && v <= 2100) continue;
      if (!allowed.has(v)) return false;
    }
    return true;
  });
  return kept.length > 0 ? kept.join(" ") : null;
}
