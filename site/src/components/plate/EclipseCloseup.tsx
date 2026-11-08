"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import StarScene, { type SceneStatus, type SceneStar } from "./StarScene";
import type { ZoomData } from "@/lib/types";

// Close-up of one eclipse: the two stars at their true relative size, the
// companion sliding across the star, and under it the star's own measured
// eclipse profile. One number - time from mid-eclipse, in eclipse durations -
// drives the picture, the model curve and the cursor, so they cannot drift apart.
//
// Real: the measured profile (binned median of the folded data around the
// eclipse), the eclipse duration and depth, the colours (temperature).
// Estimated: the radius ratio, surface-brightness ratio and separation come
// from the same central-eclipse, uniform-disc estimates as the orbit drawing
// above; the model curve below is what those estimates predict. Where it does
// not follow the measured profile (partial eclipses, limb darkening, an
// off-centre path) the panel says so.

const VW = 320;
const VH = 160;
const WINDOW = 1.0; // durations either side of mid-eclipse
const SWEEP_SECONDS = 9;

interface CloseupProps {
  k: number;
  j: number;
  duration: number; // days
  teff1: [number, number, number];
  edge1: [number, number, number];
  teff2: [number, number, number];
  edge2: [number, number, number];
  zoomPrimary: ZoomData | null;
  zoomSecondary: ZoomData | null;
  secondaryDetected: boolean;
}

// Area of overlap of two discs (radii a, b; centres d apart).
function overlap(a: number, b: number, d: number): number {
  if (d >= a + b) return 0;
  if (d <= Math.abs(a - b)) return Math.PI * Math.min(a, b) ** 2;
  const a2 = a * a;
  const b2 = b * b;
  const x = (d * d + a2 - b2) / (2 * d * a);
  const y = (d * d + b2 - a2) / (2 * d * b);
  const z = (-d + a + b) * (d + a - b) * (d - a + b) * (d + a + b);
  return a2 * Math.acos(Math.max(-1, Math.min(1, x))) + b2 * Math.acos(Math.max(-1, Math.min(1, y))) - 0.5 * Math.sqrt(Math.max(0, z));
}

// Relative flux of the pair at projected centre separation d (units of the
// primary's radius). primaryEclipsed: the companion is in front of the star.
export function modelFlux(d: number, k: number, j: number, primaryEclipsed: boolean): number {
  const total = 1 + j * k * k;
  const ov = overlap(1, k, d) / Math.PI;
  return 1 - (primaryEclipsed ? ov : j * ov) / total;
}

function interp(pts: [number, number][], x: number): number | null {
  if (pts.length < 2 || x < pts[0][0] || x > pts[pts.length - 1][0]) return null;
  let lo = 0;
  let hi = pts.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pts[mid][0] <= x) lo = mid;
    else hi = mid;
  }
  const f = (x - pts[lo][0]) / (pts[hi][0] - pts[lo][0] || 1);
  return pts[lo][1] + (pts[hi][1] - pts[lo][1]) * f;
}

export default function EclipseCloseup(p: CloseupProps) {
  const [which, setWhich] = useState<"primary" | "secondary">("primary");
  const [tau, setTau] = useState(-WINDOW);
  const [playing, setPlaying] = useState(true);
  const [gl, setGl] = useState<SceneStatus>("pending");
  const dragging = useRef(false);

  useEffect(() => {
    if (!playing) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    let last: number | null = null;
    const tick = (ts: number) => {
      if (last !== null && !dragging.current) {
        const dt = (ts - last) / 1000;
        setTau((v) => {
          const n = v + (dt / SWEEP_SECONDS) * 2 * WINDOW;
          return n > WINDOW ? -WINDOW : n;
        });
      }
      last = ts;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const secOk = Boolean(p.zoomSecondary) && p.secondaryDetected;
  const zoom = which === "secondary" && secOk ? p.zoomSecondary : p.zoomPrimary;
  const primaryEclipsed = which === "primary" || !secOk;
  const durH = p.duration * 24;

  const profile = useMemo(() => {
    if (!zoom) return null;
    const bin = zoom.binned.filter((q) => Math.abs(q[0]) <= WINDOW * durH * 1.02).map((q) => [q[0] / durH, q[1]] as [number, number]);
    const raw = zoom.raw.filter((q) => Math.abs(q[0]) <= WINDOW * durH).map((q) => [q[0] / durH, q[1]] as [number, number]);
    if (bin.length < 4) return null;
    const out = bin.filter((q) => Math.abs(q[0]) > 0.8 * WINDOW);
    const base = out.length ? out.reduce((a, q) => a + q[1], 0) / out.length : 1;
    return { bin: bin.map((q) => [q[0], q[1] / base] as [number, number]), raw: raw.map((q) => [q[0], q[1] / base] as [number, number]) };
  }, [zoom, durH]);

  // Central eclipse: contact at |t| = 0.5 durations when separation = 1 + k,
  // so x(t) = (1 + k) * sin(pi t D / P') / sin(pi D / P'), approximated linearly
  // across the window (the arc is nearly straight over two durations).
  const sepR = (t: number) => Math.abs(t) * 2 * (1 + p.k);

  const curve = useMemo(() => {
    const n = 121;
    const pts: [number, number][] = [];
    for (let i = 0; i < n; i++) {
      const t = -WINDOW + (2 * WINDOW * i) / (n - 1);
      pts.push([t, modelFlux(sepR(t), p.k, p.j, primaryEclipsed)]);
    }
    return pts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.k, p.j, primaryEclipsed]);

  const stats = useMemo(() => {
    if (!profile) return null;
    let s2 = 0;
    let n = 0;
    for (const [t, v] of profile.bin) {
      const m = modelFlux(sepR(t), p.k, p.j, primaryEclipsed);
      s2 += (v - m) ** 2;
      n++;
    }
    const rms = Math.sqrt(s2 / Math.max(1, n));
    const depth = Math.max(1e-6, 1 - Math.min(...profile.bin.map((q) => q[1])));
    // width at half depth, in eclipse durations: measured vs model
    const halfWidth = (pts: [number, number][], dep: number) => {
      const lvl = 1 - dep / 2;
      const inside = pts.filter((q) => q[1] <= lvl).map((q) => q[0]);
      return inside.length ? Math.max(...inside) - Math.min(...inside) : 0;
    };
    const wMeas = halfWidth(profile.bin, depth);
    const modelDepth = 1 - Math.min(...curve.map((q) => q[1]));
    const wModel = halfWidth(curve, modelDepth);
    const ratio = wModel > 0 ? wMeas / wModel : 1;
    return { rms, depth, ratio, bad: rms > 0.35 * depth || ratio < 0.7 || ratio > 1.4 };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile, curve, p.k, p.j, primaryEclipsed]);

  const yr = useMemo(() => {
    const vals = [...curve.map((q) => q[1]), ...(profile ? profile.bin.map((q) => q[1]) : [])];
    const lo = Math.min(...vals);
    const hi = Math.max(...vals, 1);
    const pad = (hi - lo) * 0.12 || 0.001;
    return { lo: lo - pad, hi: hi + pad };
  }, [curve, profile]);

  const sx = (t: number) => ((t + WINDOW) / (2 * WINDOW)) * 320;
  const sy = (v: number) => 4 + (1 - (v - yr.lo) / (yr.hi - yr.lo)) * 52;
  const path = (pts: [number, number][]) => pts.map((q, i) => `${i === 0 ? "M" : "L"}${sx(q[0]).toFixed(1)},${sy(q[1]).toFixed(1)}`).join(" ");

  const sepNow = sepR(tau);
  const fModel = modelFlux(sepNow, p.k, p.j, primaryEclipsed);
  const fMeas = profile ? interp(profile.bin, tau) : null;
  const hidden = Math.min(1, overlap(1, p.k, sepNow) / Math.PI / (primaryEclipsed ? 1 : p.k * p.k));

  const R1 = Math.min(44, 130 / (2 * (1 + p.k)));
  const R2 = Math.max(2, R1 * p.k);
  const compX = 160 + (tau < 0 ? -1 : 1) * sepNow * R1 * (tau === 0 ? 0 : 1);
  const cy = 80;
  const radiance = Math.round(Math.pow(Math.min(1.05, Math.max(0.3, fModel)), 3) * 100) / 100;
  const transitDim = Math.max(0.25, Math.min(1, p.j > 0 ? p.j : 0.25));
  const dim2 = primaryEclipsed && sepNow < 1 + p.k ? transitDim : 1;
  const star1: SceneStar = { cx: 160, cy, r: R1, dim: 1, color: p.teff1, edge: p.edge1, glow: 0.9, contrast: 0.18, axis: [0, 0, 1], elong: 0, heat: 0 };
  const star2: SceneStar = { cx: compX, cy, r: R2, dim: dim2, color: p.teff2, edge: p.edge2, glow: 0.7, contrast: 0.15, axis: [0, 0, 1], elong: 0, heat: 0 };
  const hoursNow = tau * durH;

  return (
    <div className="mt-4 rounded-lg border border-line bg-panel-2 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-faint">Eclipse close-up</span>
        <div className="flex gap-1.5">
          <button type="button" onClick={() => setWhich("primary")} className={`nav-caps rounded-md border px-2 py-0.5 font-mono text-[10px] ${which === "primary" ? "border-accent text-accent" : "border-line text-muted hover:text-fg"}`}>Primary</button>
          <button type="button" disabled={!secOk} onClick={() => setWhich("secondary")} title={secOk ? undefined : "No secondary eclipse was measured"} className={`nav-caps rounded-md border px-2 py-0.5 font-mono text-[10px] ${which === "secondary" && secOk ? "border-accent text-accent" : "border-line text-muted hover:text-fg"} disabled:cursor-not-allowed disabled:opacity-40`}>Secondary</button>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-md bg-black/30" style={{ aspectRatio: "16 / 7" }}>
        <div className="absolute inset-x-0 top-0" style={{ aspectRatio: "2 / 1", transform: "translateY(-6.25%)" }}>
          <StarScene
            className="absolute inset-0 h-full w-full"
            onStatus={setGl}
            companionFront={primaryEclipsed}
            radiance={radiance}
            primary={star1}
            companion={star2}
          />
        </div>
        {gl === "fail" && (
          <svg viewBox={`0 0 ${VW} ${VH}`} className="absolute inset-0 h-full w-full" aria-hidden="true">
            <circle cx={160} cy={cy} r={R1} fill={`rgb(${p.teff1.map((c) => Math.round(c * 255)).join(",")})`} />
            <circle cx={compX} cy={cy} r={R2} fill={`rgb(${p.teff2.map((c) => Math.round(c * 255)).join(",")})`} opacity={primaryEclipsed ? 0.92 : 1} />
          </svg>
        )}
      </div>

      <svg viewBox="0 0 320 60" className="mt-2 block w-full" role="img" aria-label="Measured eclipse profile with the model curve and the current time marked">
        {profile && profile.raw.map((q, i) => <circle key={i} cx={sx(q[0])} cy={sy(q[1])} r={0.8} fill="currentColor" opacity={0.18} />)}
        <path d={path(curve)} fill="none" stroke="currentColor" strokeOpacity={0.55} strokeDasharray="3 3" strokeWidth={1} />
        {profile && <path d={path(profile.bin)} fill="none" className="stroke-accent sv-draw" pathLength={1} strokeWidth={1.5} strokeLinejoin="round" />}
        <line x1={sx(tau)} x2={sx(tau)} y1={1} y2={59} className="stroke-accent" strokeOpacity={0.6} strokeWidth={1} />
        <circle cx={sx(tau)} cy={sy(fMeas ?? fModel)} r={2.8} className="fill-accent" />
      </svg>
      <div className="flex justify-between font-mono text-[9px] text-faint">
        <span>-{(WINDOW * durH).toFixed(1)} h</span>
        <span>solid: measured - dashed: model</span>
        <span>+{(WINDOW * durH).toFixed(1)} h</span>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <button type="button" onClick={() => setPlaying((v) => !v)} className="nav-caps rounded-md border border-line px-2 py-0.5 font-mono text-[10px] text-muted hover:text-fg">{playing ? "Pause sweep" : "Play sweep"}</button>
        <input
          type="range"
          min={-WINDOW}
          max={WINDOW}
          step={0.005}
          value={tau}
          aria-label="Time from mid-eclipse"
          onPointerDown={() => { dragging.current = true; }}
          onPointerUp={() => { dragging.current = false; }}
          onChange={(e) => setTau(parseFloat(e.target.value))}
          className="h-1 w-full cursor-pointer accent-[var(--accent,#7aa7ff)]"
        />
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[10px]">
        <div className="flex justify-between border-b border-line pb-1"><dt className="text-faint">From mid-eclipse</dt><dd className="text-fg">{hoursNow >= 0 ? "+" : ""}{hoursNow.toFixed(1)} h</dd></div>
        <div className="flex justify-between border-b border-line pb-1"><dt className="text-faint">{primaryEclipsed ? "Star hidden" : "Companion hidden"}</dt><dd className="text-fg">{(hidden * 100).toFixed(0)}%</dd></div>
        <div className="flex justify-between border-b border-line pb-1"><dt className="text-faint">Measured light</dt><dd className="text-fg">{fMeas !== null ? fMeas.toFixed(4) : "-"}</dd></div>
        <div className="flex justify-between border-b border-line pb-1"><dt className="text-faint">Model light</dt><dd className="text-fg">{fModel.toFixed(4)}</dd></div>
      </dl>
      <p className="mt-2 text-[10px] leading-relaxed text-faint">
        Stars at their estimated true relative size; the companion crosses the star on a straight, central path (the same assumption as the orbit drawing). Dashed: what those estimates predict, with uniform discs and no limb darkening.
        {stats ? ` Model vs measured: rms ${(stats.rms * 100).toFixed(2)}% of flux (${((stats.rms / stats.depth) * 100).toFixed(0)}% of the eclipse depth).` : ""}
        {stats?.bad ? ` The model does not follow this eclipse well (measured width at half depth is ${stats.ratio.toFixed(1)}x the model's) - it may be partial, off-centre or limb-darkened, or the stars distorted - so the picture is only indicative.` : ""}
      </p>
    </div>
  );
}
