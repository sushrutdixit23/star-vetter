import type { Detail } from "./types";
import type { Summary } from "@/components/dash/DetailPanels";

// Pure string formatting, kept out of DetailPanels.tsx on purpose. That
// file starts with "use client", which means every one of its exports is
// treated as a reference meant to be rendered as JSX - a server component
// (like the candidate plate page) cannot call one of them as a plain
// function. Living here instead, with no "use client" directive, this can
// be called from both server and client code.

const pct = (x: number, d = 3) => `${(x * 100).toFixed(d)}%`;

export function summaryLine(s: Summary, d: Detail | null): string {
  const P = d ? d.period_true_days : s.corrected_period_days ?? s.period_days;
  const parts = [`${P.toFixed(4)}-day period`];
  if (d?.aliased || s.aliased) parts[0] += " (twice the BLS period)";
  if (d?.primary) parts.push(`a ${pct(d.primary.depth, 2)} primary eclipse`);
  if (d?.secondary) {
    parts.push(
      d.secondary.detected
        ? `a ${pct(d.secondary.depth, 2)} secondary eclipse at phase ${d.secondary.phase.toFixed(3)}`
        : "no significant secondary eclipse"
    );
  }
  const base = `Eclipsing-binary candidate: ${parts.join(", ")}.`;
  return d && d.checks.length > 0 ? `${base} Automated cross-checks question this period - see below.` : base;
}
