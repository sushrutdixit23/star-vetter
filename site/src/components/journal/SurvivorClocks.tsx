"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";
import Band from "./Band";

// Survivors' own binned light curves, folded at their true periods and
// wrapped into circles (primary eclipse at the top, one orbit clockwise).
// The hand is computed live from each star's fitted epoch and period
// (BTJD = BJD_TDB - 2457000); it ignores the TDB/UTC offset and light
// travel time, so it is approximate to a few minutes. Hands only render
// after mount, so server and client markup always match. One row is
// shown; the live count covers every survivor.

export interface Survivor {
  tic: number;
  tier: Tier;
  binned: [number, number][];
  period: number;
  t0: number;
  duration: number;
  secondaryPhase: number | null;
}

const SHOWN = 12;
const C = 50;
const RING = 42;
const DEPTH = 0.55;

function nowBtjd(): number {
  return Date.now() / 86400000 + 2440587.5 - 2457000;
}

function polarPath(binned: [number, number][]): string {
  if (binned.length < 3) return "";
  const pts = [...binned].sort((a, b) => a[0] - b[0]);
  let lo = Infinity;
  let hi = -Infinity;
  for (const p of pts) {
    if (p[1] < lo) lo = p[1];
    if (p[1] > hi) hi = p[1];
  }
  const range = hi - lo || 1;
  const parts = pts.map((p, i) => {
    const r = RING * (1 - (DEPTH * (hi - p[1])) / range);
    const a = p[0] * 2 * Math.PI - Math.PI / 2;
    return `${i === 0 ? "M" : "L"}${(C + r * Math.cos(a)).toFixed(1)},${(C + r * Math.sin(a)).toFixed(1)}`;
  });
  return parts.join(" ") + " Z";
}

function phaseNow(s: Survivor, t: number): number {
  let p = ((t - s.t0) / s.period) % 1;
  if (p < 0) p += 1;
  return p >= 0.5 ? p - 1 : p;
}

function eclipseState(s: Survivor, ph: number): "primary" | "secondary" | null {
  const half = s.duration / s.period / 2;
  if (Math.abs(ph) < half) return "primary";
  if (s.secondaryPhase !== null) {
    let d = Math.abs(ph - s.secondaryPhase) % 1;
    d = Math.min(d, 1 - d);
    if (d < half) return "secondary";
  }
  return null;
}

function untilPrimary(s: Survivor, ph: number): number {
  const p01 = ph < 0 ? ph + 1 : ph;
  return ((1 - p01) % 1) * s.period;
}

function fmtSpan(days: number): string {
  if (days >= 1) return `${days.toFixed(1)} d`;
  return `${(days * 24).toFixed(1)} h`;
}

export default function SurvivorClocks({ survivors }: { survivors: Survivor[] }) {
  const shown = useMemo(() => survivors.slice(0, SHOWN), [survivors]);
  const paths = useMemo(() => shown.map((s) => polarPath(s.binned)), [shown]);
  const [t, setT] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    setT(nowBtjd());
    const id = setInterval(() => setT(nowBtjd()), 30000);
    return () => clearInterval(id);
  }, []);

  const states = useMemo(() => {
    if (t === null) return null;
    return survivors.map((s) => {
      const ph = phaseNow(s, t);
      return { ph, ecl: eclipseState(s, ph) };
    });
  }, [survivors, t]);

  const inEclipse = states ? states.filter((x) => x.ecl !== null).length : null;
  const hi = hover === null ? -1 : survivors.findIndex((s) => s.tic === hover);
  const hs = hi >= 0 ? survivors[hi] : null;
  const hst = hi >= 0 && states ? states[hi] : null;

  let caption = "Hover a clock to see which star it is; click to open its evidence.";
  if (hs) {
    caption = `TIC ${hs.tic} - ${TIER_STYLE[hs.tier].label} - P = ${hs.period.toFixed(3)} d`;
    if (hst) caption += hst.ecl ? ` - in ${hst.ecl} eclipse right now` : ` - next primary eclipse in ${fmtSpan(untilPrimary(hs, hst.ph))}`;
  }

  return (
    <Band num="V" title="The survivors" lede={`${survivors.length} candidates remain. Each clock is one star's light curve folded on its period and wrapped into a circle: every inward notch is an eclipse, and the hand shows where the star is in its orbit right now.`} action={<div><div className="font-mono text-3xl text-fg">{inEclipse === null ? "-" : inEclipse}</div><div className="text-[11px] text-muted">of {survivors.length} mid-eclipse right now</div></div>}>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_13rem] xl:items-center">
        <div>
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-12">
            {shown.map((s, i) => {
              const color = TIER_STYLE[s.tier].chart;
              const st = states ? states[i] : null;
              const lit = st !== null && st.ecl !== null;
              const a = st ? st.ph * 2 * Math.PI - Math.PI / 2 : 0;
              return (
                <Link key={s.tic} href={`/candidates/${s.tic}`} aria-label={`TIC ${s.tic}`} className="block rounded-lg p-1 transition-colors hover:bg-panel-2" onMouseEnter={() => setHover(s.tic)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(s.tic)} onBlur={() => setHover(null)}>
                  <svg viewBox="0 0 100 100" className="block w-full" aria-hidden="true">
                    <circle cx={C} cy={C} r={RING} strokeWidth={lit ? 2.2 : 1} style={{ fill: "var(--panel)", stroke: lit ? color : "var(--line)" }} className={lit ? "motion-safe:animate-pulse" : ""} />
                    <circle cx={C} cy={C} r={RING * (1 - DEPTH)} fill="none" strokeWidth={0.6} strokeDasharray="1.5 3" style={{ stroke: "var(--line)" }} />
                    <path d={paths[i]} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={1.6} strokeLinejoin="round" />
                    {st && <line x1={C} y1={C} x2={(C + (RING + 4) * Math.cos(a)).toFixed(1)} y2={(C + (RING + 4) * Math.sin(a)).toFixed(1)} strokeWidth={1.2} strokeLinecap="round" style={{ stroke: "var(--fg)", strokeOpacity: 0.7 }} />}
                    {st && <circle cx={C} cy={C} r={2} style={{ fill: "var(--fg)" }} />}
                  </svg>
                </Link>
              );
            })}
          </div>
          <p className="mt-3 min-h-[1.25rem] font-mono text-[11px] text-muted" aria-live="polite">{caption}</p>
        </div>
        <div className="flex flex-col gap-3 xl:items-end">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted xl:justify-end">
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: TIER_STYLE.CLEAN.chart }} />Clean</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: TIER_STYLE["PERIOD ALIAS"].chart }} />Period alias</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: TIER_STYLE["THIN MARGIN"].chart }} />Flagged</span>
          </div>
          <Link href="/candidates" className="nav-caps font-mono text-[11px] text-fg hover:text-accent">View all {survivors.length} candidates &rarr;</Link>
          <p className="text-[10px] text-faint xl:text-right">Glowing ring: mid-eclipse now, approximate, from the fitted ephemeris.</p>
        </div>
      </div>
    </Band>
  );
}
