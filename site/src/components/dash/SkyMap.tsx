"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { SkyPoint, Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";
import { fmtDec, fmtRA, galacticLine, galacticToEquatorial, mollweide, projectedPath } from "@/lib/sky";

// All-sky Mollweide map (equatorial J2000, RA 0h at centre, increasing to
// the left) with every confirmed candidate at its real TIC position.
// Real geometry: the outline, the RA/Dec grid, the galactic plane (b = 0,
// via the J2000 -> galactic rotation in lib/sky.ts) and every candidate
// position. Schematic: the soft Milky Way band, a seeded glow along the
// galactic plane that brightens toward the galactic centre - it shows
// where the Milky Way lies, not measured star counts. Labels are HTML
// overlays so they stay a readable size at any map width.

const W = 1000;
const H = 500;
const R = 2 * Math.SQRT2;
const DEG = Math.PI / 180;
const sx = (x: number) => W / 2 + (x / R) * (W / 2 - 6);
const sy = (y: number) => H / 2 - (y / Math.SQRT2) * (H / 2 - 6);

type GroupKey = "clean" | "alias" | "flagged";

const GROUPS: { key: GroupKey; label: string; color: string }[] = [
  { key: "clean", label: "Clean", color: TIER_STYLE.CLEAN.chart },
  { key: "alias", label: "Period alias", color: TIER_STYLE["PERIOD ALIAS"].chart },
  { key: "flagged", label: "Flagged", color: TIER_STYLE["THIN MARGIN"].chart },
];

function groupOf(t: Tier): GroupKey {
  if (t === "CLEAN") return "clean";
  if (t === "PERIOD ALIAS") return "alias";
  return "flagged";
}

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(r: () => number) {
  const u = Math.max(r(), 1e-9);
  const v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const r1 = (v: number) => Math.round(v * 10) / 10;
const r3 = (v: number) => Math.round(v * 1000) / 1000;

interface BandDot {
  x: number;
  y: number;
  rad: number;
  op: number;
}

function buildBand(): { soft: BandDot[]; fine: BandDot[] } {
  const r = rng(20260928);
  const soft: BandDot[] = [];
  const fine: BandDot[] = [];
  for (let i = 0; i < 1100; i++) {
    const l = r() * 360;
    const toward = (1 + Math.cos(l * DEG)) / 2;
    const sigma = 4 + 7 * Math.pow(toward, 3);
    const b = Math.max(-30, Math.min(30, gauss(r) * sigma));
    const [ra, dec] = galacticToEquatorial(l, b);
    const [mx, my] = mollweide(ra, dec);
    const bright = 0.25 + 0.75 * toward * toward;
    const x = r1(sx(mx));
    const y = r1(sy(my));
    if (i % 2 === 0) {
      soft.push({ x, y, rad: r1(5 + r() * 8), op: r3(bright * 0.11) });
    } else {
      fine.push({ x, y, rad: r1(0.6 + r() * 1.0), op: r3(bright * 0.5) });
    }
  }
  return { soft, fine };
}

function outlinePath(): string {
  const a: [number, number][] = [];
  for (let d = -90; d <= 90; d += 3) a.push([180.0001, d]);
  const b: [number, number][] = [];
  for (let d = 90; d >= -90; d -= 3) b.push([179.9999, d]);
  return projectedPath(a, sx, sy) + projectedPath(b, sx, sy);
}

const BAND = buildBand();
const OUTLINE = outlinePath();
const PLANE = projectedPath(galacticLine(0), sx, sy);

const DEC_LINES = [-60, -30, 0, 30, 60].map((dec) => {
  const pts: [number, number][] = [];
  for (let ra = 180.001; ra <= 540; ra += 4) pts.push([ra % 360, dec]);
  return { dec, d: projectedPath(pts, sx, sy) };
});

const RA_LINES = [0, 60, 120, 240, 300].map((ra) => {
  const pts: [number, number][] = [];
  for (let dec = -90; dec <= 90; dec += 3) pts.push([ra, dec]);
  return { ra, d: projectedPath(pts, sx, sy) };
});

const DEC_LABELS = [60, 30, 0, -30, -60].map((d) => {
  const [x1, y1] = mollweide(180.001, d);
  const [x2] = mollweide(179.999, d);
  return { d, left: r3((sx(Math.min(x1, x2)) / W) * 100), top: r3((sy(y1) / H) * 100) };
});

const RA_LABELS = [0, 6, 18].map((h) => {
  const [x, y] = mollweide(h * 15 + 0.001, 0);
  return { h, left: r3((sx(x) / W) * 100), top: r3((sy(y) / H) * 100) };
});

interface Plotted {
  p: SkyPoint;
  ra: number;
  dec: number;
  x: number;
  y: number;
  g: GroupKey;
}

export default function SkyMap({ points, highlight, className = "" }: { points: SkyPoint[]; highlight?: number; className?: string }) {
  const router = useRouter();
  const [hover, setHover] = useState<number | null>(null);
  const [hidden, setHidden] = useState<GroupKey[]>([]);

  const plotted = useMemo<Plotted[]>(() => {
    const out: Plotted[] = [];
    for (const p of points) {
      if (p.ra === null || p.dec === null) continue;
      const [mx, my] = mollweide(p.ra, p.dec);
      out.push({ p, ra: p.ra, dec: p.dec, x: r1(sx(mx)), y: r1(sy(my)), g: groupOf(p.tier) });
    }
    return out;
  }, [points]);

  const counts: Record<GroupKey, number> = { clean: 0, alias: 0, flagged: 0 };
  for (const q of plotted) counts[q.g] += 1;

  const visible = plotted.filter((q) => !hidden.includes(q.g)).sort((a, b) => (a.p.tic === hover ? 1 : b.p.tic === hover ? -1 : 0));
  const hp = hover === null ? null : plotted.find((q) => q.p.tic === hover) ?? null;
  const hi = highlight === undefined ? null : plotted.find((q) => q.p.tic === highlight) ?? null;

  const open = (tic: number) => router.push(`/candidates/${tic}`);
  const toggle = (k: GroupKey) => setHidden((h) => (h.includes(k) ? h.filter((x) => x !== k) : [...h, k]));

  return (
    <div className={className}>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="All-sky map of confirmed candidate positions">
          <defs>
            <filter id="sv-sky-blur" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="7" />
            </filter>
            <clipPath id="sv-sky-clip">
              <path d={OUTLINE} />
            </clipPath>
          </defs>
          <path d={OUTLINE} fill="rgba(9,13,26,0.85)" stroke="none" />
          <g clipPath="url(#sv-sky-clip)">
            <g filter="url(#sv-sky-blur)">
              {BAND.soft.map((b, i) => (
                <circle key={`s${i}`} cx={b.x} cy={b.y} r={b.rad} fill="#cdd6f4" opacity={b.op} />
              ))}
            </g>
            {BAND.fine.map((b, i) => (
              <circle key={`f${i}`} cx={b.x} cy={b.y} r={b.rad} fill="#e6ebfa" opacity={b.op} />
            ))}
            {DEC_LINES.map((l) => (
              <path key={`d${l.dec}`} d={l.d} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
            ))}
            {RA_LINES.map((l) => (
              <path key={`r${l.ra}`} d={l.d} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
            ))}
            <path d={PLANE} fill="none" stroke="rgba(251,191,36,0.5)" strokeWidth={1.3} />
          </g>
          <path d={OUTLINE} fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={1.2} />
          {hi && <circle cx={hi.x} cy={hi.y} r={16} fill="none" stroke="#fde68a" strokeWidth={1.5} opacity={0.7} />}
          {visible.map((q) => {
            const on = hover === q.p.tic;
            const col = TIER_STYLE[q.p.tier].chart;
            return (
              <g key={q.p.tic} tabIndex={0} role="link" aria-label={`TIC ${q.p.tic}, ${TIER_STYLE[q.p.tier].label}`} className="cursor-pointer outline-none" onMouseEnter={() => setHover(q.p.tic)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(q.p.tic)} onBlur={() => setHover(null)} onClick={() => open(q.p.tic)} onKeyDown={(e) => { if (e.key === "Enter") open(q.p.tic); }}>
                <circle cx={q.x} cy={q.y} r={on ? 20 : 11} fill={col} opacity={on ? 0.28 : 0.14} style={{ transition: "r 150ms, opacity 150ms" }} />
                <circle cx={q.x} cy={q.y} r={on ? 7 : 5} fill={col} stroke="rgba(5,7,12,0.9)" strokeWidth={1.2} style={{ transition: "r 150ms" }} />
              </g>
            );
          })}
        </svg>
        {DEC_LABELS.map((l) => (
          <span key={`dl${l.d}`} className="pointer-events-none absolute font-mono text-[10px] text-faint" style={{ left: `${l.left}%`, top: `${l.top}%`, transform: "translate(6px, -50%)" }}>{`${l.d > 0 ? "+" : ""}${l.d}\u00b0`}</span>
        ))}
        {RA_LABELS.map((l) => (
          <span key={`rl${l.h}`} className="pointer-events-none absolute font-mono text-[11px] text-muted" style={{ left: `${l.left}%`, top: `${l.top}%`, transform: "translate(-50%, calc(-100% - 4px))" }}>{l.h}h</span>
        ))}
        {hp && !hidden.includes(hp.g) && (
          <div className="pointer-events-none absolute z-10 w-max max-w-[16rem] rounded-md border border-line bg-panel/95 px-3 py-2 text-[11px] shadow-lg backdrop-blur" style={{ left: `${Math.min(88, Math.max(12, (hp.x / W) * 100))}%`, top: `${(hp.y / H) * 100}%`, transform: hp.y / H < 0.3 ? "translate(-50%, 18px)" : "translate(-50%, calc(-100% - 18px))" }}>
            <div className="font-mono text-xs text-fg">TIC {hp.p.tic}</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-muted">
              <span className="h-2 w-2 rounded-full" style={{ background: TIER_STYLE[hp.p.tier].chart }} />
              {TIER_STYLE[hp.p.tier].label}
            </div>
            <div className="mt-1 font-mono text-[10px] text-faint">RA {fmtRA(hp.ra)}</div>
            <div className="font-mono text-[10px] text-faint">Dec {fmtDec(hp.dec)}</div>
            <div className="font-mono text-[10px] text-faint">BLS SNR {Math.round(hp.p.bls_snr).toLocaleString("en-US")}</div>
            <div className="mt-1 text-[10px] text-accent">Click to open its evidence</div>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
        {GROUPS.map((g) => {
          const n = counts[g.key];
          if (n === 0) return null;
          const off = hidden.includes(g.key);
          return (
            <button key={g.key} type="button" onClick={() => toggle(g.key)} aria-pressed={!off} className={`inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 transition-colors ${off ? "text-faint" : "text-fg hover:border-fg/30"}`}>
              <span className="h-2 w-2 rounded-full" style={{ background: g.color, opacity: off ? 0.3 : 1 }} />
              {g.label}
              <span className="font-mono text-faint">{n}</span>
            </button>
          );
        })}
        <span className="ml-2 inline-flex items-center gap-1.5 text-muted">
          <span className="h-0.5 w-4" style={{ background: "rgba(251,191,36,0.55)" }} />
          Galactic plane
        </span>
        <span className="inline-flex items-center gap-1.5 text-muted">
          <span className="h-2 w-5 rounded-full" style={{ background: "radial-gradient(closest-side, rgba(205,214,244,0.55), rgba(205,214,244,0))" }} />
          Milky Way band (schematic)
        </span>
      </div>
      <p className="mt-2 text-[10px] text-faint">Equatorial J2000, Mollweide projection: right ascension increases to the left from 0h at the centre. Click a legend entry to hide or show that group; click a point to open its evidence.</p>
    </div>
  );
}
