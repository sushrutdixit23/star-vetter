"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { PredictedEclipse, PredictionStar } from "@/lib/types";

type Filter = "all" | "VALIDATED" | "UNVALIDATED";

// "2026-12-30 01:02:03" (geocentric UTC) -> Date
function utcDate(s: string): Date {
  return new Date(s.replace(" ", "T") + "Z");
}

function fmtUtc(s: string): string {
  return s.slice(0, 16) + " UTC";
}

function fmtSigma(min: number): string {
  return min < 90 ? `${min.toFixed(0)} min` : `${(min / 60).toFixed(1)} h`;
}

function countdown(ms: number): string {
  if (ms <= 0) return "now";
  const m = Math.floor(ms / 60000);
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  const mm = m % 60;
  if (d > 0) return `${d} d ${h} h`;
  return `${h} h ${mm} min`;
}

const GRADE: Record<string, { label: string; cls: string; note: string }> = {
  VALIDATED: {
    label: "Validated",
    cls: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
    note: "Predicted TESS sectors it had not been shown",
  },
  UNVALIDATED: {
    label: "Not validated",
    cls: "border-line bg-panel-2 text-muted",
    note: "Not tested over the distance it predicts",
  },
};

const CATALOG_NAMES: Record<string, string> = {
  ztf: "ZTF", crts: "CRTS", wise: "WISE", atlas: "ATLAS", asas: "ASAS-3", kelt: "KELT",
};

function names(list: string[]): string {
  return list.map((k) => CATALOG_NAMES[k] ?? k).join(", ");
}

function NoveltyBadge({ s }: { s: PredictionStar }) {
  const n = s.novelty_extra;
  if (!n) return null;
  if (n.verdict === "ALREADY_KNOWN")
    return <span className="rounded-full border border-accent-cool/50 bg-accent-cool/10 px-2 py-0.5 text-[10px] text-accent-cool">Already listed: {names(n.matched_catalogs)}</span>;
  if (n.verdict === "KNOWN_VARIABLE_PERIOD_DIFFERS")
    return <span className="rounded-full border border-accent-cool/40 px-2 py-0.5 text-[10px] text-accent-cool">Listed as variable ({names(n.known_other_period)}), other period</span>;
  if (n.verdict === "NEARBY_PERIOD_MATCH" || n.verdict === "NEARBY_VARIABLE")
    return <span className="rounded-full border border-line px-2 py-0.5 text-[10px] text-muted">Variable listed nearby ({names(n.nearby_catalogs)})</span>;
  return null;
}

function nextEclipse(preds: PredictedEclipse[], nowMs: number | null): PredictedEclipse {
  if (nowMs === null) return preds[0];
  return preds.find((p) => utcDate(p.utc).getTime() > nowMs) ?? preds[preds.length - 1];
}

export default function PredictionsBoard({ stars }: { stars: PredictionStar[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  // null on the server and first client render: no clock-dependent text until mounted
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  const rows = useMemo(() => {
    const list = stars.filter((s) => filter === "all" || s.grade === filter);
    return list
      .map((s) => ({ s, next: nextEclipse(s.predictions, now) }))
      .sort((a, b) => a.next.t_btjd - b.next.t_btjd);
  }, [stars, filter, now]);

  const chips: { id: Filter; label: string; n: number }[] = [
    { id: "all", label: "All", n: stars.length },
    { id: "VALIDATED", label: "Validated", n: stars.filter((s) => s.grade === "VALIDATED").length },
    { id: "UNVALIDATED", label: "Not validated", n: stars.filter((s) => s.grade === "UNVALIDATED").length },
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {chips.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setFilter(c.id)}
            aria-pressed={filter === c.id}
            className={`nav-caps rounded-full border px-3 py-1 font-mono text-[11px] transition-colors ${filter === c.id ? "border-accent text-fg" : "border-line text-muted hover:text-fg"}`}
          >
            {c.label} <span className="text-faint">{c.n}</span>
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border border-line">
        <div className="nav-caps hidden grid-cols-[1.1fr_0.7fr_0.8fr_1.6fr_0.9fr] gap-4 border-b border-line bg-panel px-4 py-2 font-mono text-[10px] text-faint md:grid">
          <span>Star</span>
          <span>Period</span>
          <span>Status</span>
          <span>Next primary eclipse</span>
          <span className="text-right">In</span>
        </div>
        {rows.length === 0 && <p className="px-4 py-8 text-sm text-faint">Nothing matches this filter.</p>}
        {rows.map(({ s, next }) => {
          const g = GRADE[s.grade];
          const when = utcDate(next.utc).getTime();
          return (
            <details key={s.tic} className="group border-b border-line last:border-b-0 open:bg-panel/60">
              <summary className="grid cursor-pointer list-none grid-cols-2 gap-x-4 gap-y-2 px-4 py-3 transition-colors hover:bg-panel md:grid-cols-[1.1fr_0.7fr_0.8fr_1.6fr_0.9fr] md:items-center">
                <span className="font-mono text-sm text-fg">
                  TIC {s.tic}
                  {s.tmag !== null && <span className="ml-2 text-[11px] text-faint">T = {s.tmag.toFixed(1)}</span>}
                </span>
                <span className="font-mono text-xs text-muted">{s.ephemeris.period_days.toFixed(5)} d</span>
                <span>
                  <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] ${g.cls}`}>{g.label}</span>
                </span>
                <span className="col-span-2 font-mono text-xs text-fg md:col-span-1">
                  {fmtUtc(next.utc)} <span className="text-muted">&plusmn; {fmtSigma(next.sigma_min)}</span>
                  {next.approximate && <span className="ml-1 text-faint">(sector dates approximate)</span>}
                </span>
                <span className="text-right font-mono text-xs text-accent">
                  {now === null ? "" : when < now ? "passed" : countdown(when - now)}
                </span>
              </summary>
              <div className="space-y-4 px-4 pb-5 pt-1 text-xs text-muted">
                <div className="flex flex-wrap items-center gap-2">
                  <NoveltyBadge s={s} />
                  <Link href={`/candidates/${s.tic}`} className="nav-caps font-mono text-[11px] text-accent hover:text-fg">Candidate page &rarr;</Link>
                </div>
                <div>
                  <div className="nav-caps font-mono text-[10px] text-faint">Predicted primary eclipses in TESS Year 9</div>
                  <ul className="mt-2 space-y-1 font-mono">
                    {s.predictions.map((p) => (
                      <li key={p.cycle} className="flex flex-wrap justify-between gap-x-4 text-fg">
                        <span>Sector {p.sector}{p.approximate ? "*" : ""}</span>
                        <span>{fmtUtc(p.utc)} <span className="text-muted">&plusmn; {fmtSigma(p.sigma_min)}</span></span>
                        <span className="text-faint">BTJD {p.t_btjd.toFixed(4)}</span>
                        <span className="text-faint">pending</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono sm:grid-cols-4">
                  <div><dt className="text-faint">Eclipses timed</dt><dd className="text-fg">{s.ephemeris.n_eclipses}</dd></div>
                  <div><dt className="text-faint">Sectors connected</dt><dd className="text-fg">{s.ephemeris.sectors_connected.length}</dd></div>
                  <div><dt className="text-faint">Baseline</dt><dd className="text-fg">{(s.ephemeris.baseline_days / 365.25).toFixed(1)} yr</dd></div>
                  <div><dt className="text-faint">Hold-out</dt><dd className="text-fg">{s.holdout.status === "PASS" && s.holdout.tested_reach_days !== null ? `passed, ${Math.round(s.holdout.tested_reach_days)} d reach` : "not testable"}</dd></div>
                </dl>
                {s.ephemeris.timing_excess && (
                  <p className="text-accent-cool">This star&apos;s eclipse times scatter more than their measurement errors, so the uncertainty above includes that extra scatter.</p>
                )}
                {s.ephemeris.sectors_unconnected.length > 0 && (
                  <p className="text-faint">Sectors {s.ephemeris.sectors_unconnected.join(", ")} could not be linked to this ephemeris unambiguously and were left out.</p>
                )}
                <p className="text-faint">{s.holdout.grade_note || `${g.note}.`}</p>
              </div>
            </details>
          );
        })}
      </div>
      <p className="mt-3 text-[11px] text-faint">* Sector dates 117-121 are interpolated from the announced schedule and may shift by days.</p>
    </div>
  );
}
