"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import StarBody from "../StarBody";

// The two stars, drawn from what the light curve actually says about them.
//
// Real: the star's temperature is the target's catalogue (TIC) value; the
// animation starts from where the system is in its orbit right now (fitted
// epoch and period, BTJD = BJD_TDB - 2457000); and the stars' glow follows
// the star's own measured light curve (a 360-bin fold of the raw data), so
// each eclipse dims them exactly as much as the graph says. A mini copy of
// that curve, with a moving marker, sits under the drawing.
//
// Presentation: time runs faster than real and slows down through each
// eclipse window (from the measured duration) so eclipses are visible.
// Colours follow temperature on a stellar colour scale, correctly ordered
// and saturated so differences show.
//
// Estimated from the eclipses (central eclipses, spherical stars, relative
// orbit only): surface brightness ratio j = depth2 / depth1; companion
// temperature from j in the TESS band (786 nm), or an upper limit from the
// pipeline's 5-sigma secondary limit when no secondary was seen; radius
// ratio k from depth1 = k^2 / (1 + j k^2); separation from
// sin(pi D / P) = (R1 + R2) / a; e cos(omega) = (pi / 2)(phase2 - 0.5),
// drawn as the smallest eccentricity consistent with it and moved with
// Kepler's equation. In transit the companion is darkened by j.
//
// Deliberately NOT used: the catalogue radius (it assumes a single star, so
// physical sizes would be confident but wrong for a binary).

const ORBIT_SECONDS = 24;
const CX = 160;
const CY = 80;
const A_MAX = 118;
const R_ZOOM = 24;
const TESS_C = 18305;

const SPECKS: [number, number, number, string][] = [
  [18, 22, 0.8, "#ffffff"], [52, 128, 0.6, "#cfe0ff"], [88, 18, 0.5, "#ffe6c2"], [131, 142, 0.7, "#ffffff"],
  [204, 16, 0.6, "#cfe0ff"], [236, 136, 0.5, "#ffe6c2"], [279, 30, 0.8, "#ffffff"], [302, 118, 0.6, "#cfe0ff"],
  [12, 92, 0.5, "#ffe6c2"], [312, 70, 0.5, "#ffffff"], [70, 60, 0.4, "#cfe0ff"], [255, 58, 0.4, "#ffe6c2"],
];

const COLOR_SCALE: [number, number, number, number][] = [
  [2500, 255, 90, 50],
  [3500, 255, 128, 64],
  [4500, 255, 170, 90],
  [5300, 255, 205, 120],
  [5800, 255, 224, 150],
  [6300, 255, 238, 190],
  [7000, 245, 244, 240],
  [8000, 214, 226, 255],
  [10000, 175, 200, 255],
  [15000, 145, 178, 255],
  [30000, 120, 160, 255],
];

interface Geometry {
  ok: boolean;
  note: string | null;
  j: number;
  k: number;
  aR1: number | null;
  e: number;
  omega: number;
  t2: number | null;
  t2Max: number | null;
}

function nowBtjd(): number {
  return Date.now() / 86400000 + 2440587.5 - 2457000;
}

function tempColor(kelvin: number): string {
  const t = Math.min(30000, Math.max(2500, kelvin));
  let i = 0;
  while (i < COLOR_SCALE.length - 2 && t > COLOR_SCALE[i + 1][0]) i++;
  const a = COLOR_SCALE[i];
  const b = COLOR_SCALE[i + 1];
  const f = (t - a[0]) / (b[0] - a[0]);
  const mix = (x: number, y: number) => Math.round(x + (y - x) * f);
  return `rgb(${mix(a[1], b[1])},${mix(a[2], b[2])},${mix(a[3], b[3])})`;
}

const r1 = (v: number) => Math.round(v * 10) / 10;
const fmtInt = (v: number) => Math.round(v).toLocaleString("en-US");

function companionTemp(t1: number, j: number): number {
  const x1 = TESS_C / t1;
  const x2 = Math.log(1 + (Math.exp(x1) - 1) / j);
  return Math.min(40000, Math.max(2300, TESS_C / x2));
}

function derive(teff: number | null, period: number, depth1: number | null, depth2: number | null, depth2Upper: number | null, secPhase: number | null, duration: number, sinusoid: boolean): Geometry {
  const fallback: Geometry = { ok: false, note: null, j: 0, k: 0.46, aR1: null, e: 0, omega: 0, t2: null, t2Max: null };
  if (sinusoid) {
    return { ...fallback, note: "This light curve is smooth and sinusoidal rather than eclipse-shaped - typical of a close pair distorted by each other's gravity, or of a signal that is not an eclipse - so the eclipse-geometry estimates do not apply. The drawing is generic; the glow still follows the real light curve." };
  }
  if (depth1 === null || !(depth1 > 0) || depth1 >= 0.95 || !(period > 0) || !(duration > 0)) {
    return { ...fallback, note: "Not enough eclipse information to estimate this system's geometry. The drawing below is generic." };
  }
  const j = depth2 !== null && depth2 > 0 ? depth2 / depth1 : 0;
  const denom = 1 - depth1 * j;
  if (denom <= 0.05) {
    return { ...fallback, note: "The eclipse depths are outside the range these simple estimates handle. The drawing below is generic." };
  }
  const k = Math.min(1.5, Math.max(0.08, Math.sqrt(depth1 / denom)));
  const sumR = Math.min(0.9, Math.sin(Math.min(Math.PI / 2, (Math.PI * duration) / period)));
  const aR1 = (1 + k) / sumR;
  let ecw = secPhase !== null ? (Math.PI / 2) * (secPhase - 0.5) : 0;
  ecw = Math.max(-0.6, Math.min(0.6, ecw));
  if (Math.abs(ecw) < 0.01) ecw = 0;
  const t2 = teff && j > 0 ? companionTemp(teff, j) : null;
  const t2Max = teff && j === 0 && depth2Upper !== null && depth2Upper > 0 ? companionTemp(teff, Math.min(1, depth2Upper / depth1)) : null;
  return { ok: true, note: null, j, k, aR1, e: Math.abs(ecw), omega: ecw < 0 ? Math.PI : 0, t2, t2Max };
}

function eccFromTrue(nu: number, e: number): number {
  return 2 * Math.atan2(Math.sqrt(1 - e) * Math.sin(nu / 2), Math.sqrt(1 + e) * Math.cos(nu / 2));
}

function trueFromEcc(ea: number, e: number): number {
  return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(ea / 2), Math.sqrt(1 - e) * Math.cos(ea / 2));
}

function solveKepler(m: number, e: number): number {
  let ea = m;
  for (let i = 0; i < 12; i++) ea = ea - (ea - e * Math.sin(ea) - m) / (1 - e * Math.cos(ea));
  return ea;
}

function fluxAt(c: [number, number][], ph: number): number {
  const n = c.length;
  if (ph <= c[0][0] || ph >= c[n - 1][0]) {
    const a = c[n - 1];
    const b = c[0];
    const span = b[0] + 1 - a[0];
    const x = ph >= a[0] ? ph - a[0] : ph + 1 - a[0];
    const f = span > 0 ? x / span : 0;
    return a[1] + (b[1] - a[1]) * f;
  }
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (c[mid][0] <= ph) lo = mid;
    else hi = mid;
  }
  const a = c[lo];
  const b = c[hi];
  const f = (ph - a[0]) / (b[0] - a[0] || 1);
  return a[1] + (b[1] - a[1]) * f;
}

export default function OrbitSchematic({ teff, period, t0, depth1, depth2, depth2Upper = null, secPhase, duration, sinusoid, curve = null, className = "" }: { teff: number | null; period: number; t0: number; depth1: number | null; depth2: number | null; depth2Upper?: number | null; secPhase: number | null; duration: number; sinusoid: boolean; curve?: [number, number][] | null; className?: string }) {
  const geo = useMemo(() => derive(teff, period, depth1, depth2, depth2Upper, secPhase, duration, sinusoid), [teff, period, depth1, depth2, depth2Upper, secPhase, duration, sinusoid]);
  const [phase, setPhase] = useState(0);
  const [mode, setMode] = useState<"zoom" | "true">("zoom");
  const pausedRef = useRef(false);
  const warpRef = useRef({ hw: 0, sp: 0.5, on: false });

  useEffect(() => {
    warpRef.current = { hw: geo.ok ? duration / period / 2 : 0, sp: secPhase ?? 0.5, on: geo.ok && !sinusoid };
  }, [geo.ok, duration, period, secPhase, sinusoid]);

  useEffect(() => {
    const start = ((((nowBtjd() - t0) / period) % 1) + 1) % 1;
    setPhase(start);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    let last: number | null = null;
    const tick = (ts: number) => {
      if (last !== null && !pausedRef.current) {
        const dt = (ts - last) / 1000;
        setPhase((p) => {
          const w = warpRef.current;
          let speed = 1;
          if (w.on && w.hw > 0) {
            const d1 = Math.min(p, 1 - p);
            let d2 = Math.abs(p - w.sp) % 1;
            d2 = Math.min(d2, 1 - d2);
            const dd = Math.min(d1, d2) / (2.5 * w.hw);
            speed = 1 - 0.9 * Math.exp(-dd * dd);
          }
          return (p + (dt / ORBIT_SECONDS) * speed) % 1;
        });
      }
      last = ts;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [period, t0]);

  const sortedCurve = useMemo(() => (curve && curve.length > 5 ? [...curve].sort((a, b) => a[0] - b[0]) : null), [curve]);
  const curveStats = useMemo(() => {
    if (!sortedCurve) return null;
    const fl = sortedCurve.map((p) => p[1]).sort((a, b) => a - b);
    const base = fl[Math.floor(fl.length / 2)] || 1;
    const lo = fl[0] / base;
    const hi = fl[fl.length - 1] / base;
    return { base, lo, hi };
  }, [sortedCurve]);
  const curvePath = useMemo(() => {
    if (!sortedCurve || !curveStats) return "";
    const span = curveStats.hi - curveStats.lo || 1;
    return sortedCurve.map((p, i) => `${i === 0 ? "M" : "L"}${r1((p[0] + 0.5) * 320)},${r1(4 + (1 - (p[1] / curveStats.base - curveStats.lo) / span) * 40)}`).join(" ");
  }, [sortedCurve, curveStats]);

  const e = geo.e;
  const omega = geo.omega;
  const k = geo.k;
  const aPx = A_MAX / (1 + e);
  const trueScale = mode === "true" && geo.aR1 !== null;
  const R1 = trueScale && geo.aR1 ? Math.max(0.8, aPx / geo.aR1) : R_ZOOM;
  const R2 = Math.max(0.6, R1 * k);
  const tilt = trueScale && geo.aR1 ? (0.5 * (1 + k)) / geo.aR1 : 0.1;
  const zoomFactor = geo.aR1 ? R_ZOOM / (aPx / geo.aR1) : null;

  const m1 = useMemo(() => {
    const e1 = eccFromTrue(Math.PI / 2 - omega, e);
    return e1 - e * Math.sin(e1);
  }, [e, omega]);

  const modelSecPhase = useMemo(() => {
    const e2 = eccFromTrue(1.5 * Math.PI - omega, e);
    const m2 = e2 - e * Math.sin(e2);
    return ((((m2 - m1) / (2 * Math.PI)) % 1) + 1) % 1;
  }, [e, omega, m1]);

  const orbitPaths = useMemo(() => {
    let back = "";
    let front = "";
    let prev: boolean | null = null;
    for (let i = 0; i <= 180; i++) {
      const nu = (2 * Math.PI * i) / 180;
      const rr = (aPx * (1 - e * e)) / (1 + e * Math.cos(nu));
      const th = nu + omega;
      const z = rr * Math.sin(th);
      const x = r1(CX + rr * Math.cos(th));
      const y = r1(CY + z * tilt);
      const isFront = z > 0;
      const cmd = prev === isFront ? "L" : "M";
      if (isFront) front += `${cmd}${x},${y} `;
      else back += `${cmd}${x},${y} `;
      prev = isFront;
    }
    return { back, front };
  }, [aPx, e, omega, tilt]);

  const ea = solveKepler(m1 + 2 * Math.PI * phase, e);
  const nu = trueFromEcc(ea, e);
  const rr = (aPx * (1 - e * e)) / (1 + e * Math.cos(nu));
  const th = nu + omega;
  const z = rr * Math.sin(th);
  const compX = r1(CX + rr * Math.cos(th));
  const compY = r1(CY + z * tilt);
  const front = z > 0;
  const compR = r1(R2 * (trueScale ? 1 : 1 + 0.08 * (z / aPx)));
  const overlapping = front && Math.hypot(compX - CX, compY - CY) < R1 + compR;
  const transitDim = geo.ok ? Math.max(0.25, Math.min(1, geo.j > 0 ? geo.j : 0.25)) : 0.6;

  const ps = phase >= 0.5 ? phase - 1 : phase;
  const fRel = sortedCurve && curveStats ? fluxAt(sortedCurve, ps) / curveStats.base : 1;
  const radiance = Math.round(Math.pow(Math.min(1.05, Math.max(0.3, fRel)), 3) * 100) / 100;
  const markerX = r1((ps + 0.5) * 320);
  const markerY = curveStats ? r1(4 + (1 - (fRel - curveStats.lo) / (curveStats.hi - curveStats.lo || 1)) * 40) : 24;

  const hw = geo.ok ? duration / period / 2 : 0;
  const dPrim = Math.min(phase, 1 - phase);
  let dSec = secPhase !== null ? Math.abs(phase - secPhase) % 1 : 1;
  dSec = Math.min(dSec, 1 - dSec);
  const stateLabel = hw > 0 && dPrim < hw ? "Primary eclipse" : hw > 0 && secPhase !== null && dSec < hw ? "Secondary eclipse" : "Out of eclipse";

  const t1 = teff ?? 5800;
  const t2 = geo.t2 ?? geo.t2Max ?? (geo.ok ? t1 * 0.6 : t1 * 0.85);
  const starColor = tempColor(t1);
  const starEdge = tempColor(t1 * 0.78);
  const compColor = tempColor(t2);
  const compEdge = tempColor(t2 * 0.78);
  const glow1 = trueScale ? Math.max(2, 10 / R1) : 1.1;
  const glow2 = trueScale ? Math.max(2, 8 / compR) : 0.8;
  const speed = fmtInt((period * 86400) / ORBIT_SECONDS);

  const companion = <StarBody cx={compX} cy={compY} r={compR} color={compColor} edge={compEdge} glow={glow2} texture={!trueScale && compR > 8} dim={overlapping ? transitDim : 1} radiance={radiance} />;

  const rows: [string, string][] = [];
  if (geo.ok) {
    rows.push(["Surface brightness ratio", geo.j > 0 ? geo.j.toFixed(2) : "companion faint - no secondary eclipse"]);
    if (geo.t2) rows.push(["Companion temperature", `~${fmtInt(geo.t2)} K`]);
    else if (geo.t2Max) rows.push(["Companion temperature", `below ~${fmtInt(geo.t2Max)} K`]);
    rows.push(["Companion / star radius", `~${geo.k.toFixed(2)}`]);
    rows.push(["Face hidden at primary eclipse", geo.k >= 1 ? "all of it" : `~${(geo.k * geo.k * 100).toFixed(0)}%`]);
    if (geo.aR1) rows.push(["Separation", `~${geo.aR1.toFixed(geo.aR1 < 10 ? 1 : 0)} x the star's radius`]);
    rows.push(["Eccentricity", geo.e > 0 ? `at least ${geo.e.toFixed(3)}` : "consistent with circular"]);
    if (secPhase !== null) rows.push(["Secondary eclipse phase", `${secPhase.toFixed(3)} measured, ${modelSecPhase.toFixed(3)} in this orbit`]);
  }

  const caption: string[] = [];
  if (trueScale) caption.push("True scale: the stars are tiny next to their separation, they eclipse only because we see the orbit almost exactly edge-on, and the overlap lasts as long as the real eclipse.");
  else if (zoomFactor) caption.push(`Zoomed: both stars drawn about ${Math.round(zoomFactor)}x larger than their real size relative to the orbit, so they overlap for longer than the real eclipse lasts.`);
  else caption.push("Not to scale.");
  if (sortedCurve) caption.push("A star's surface never gets dimmer during an eclipse - part of it is simply hidden. What drops is the total light we receive, shown exactly by the readout and bar below from the real light curve; the glow dims with it, exaggerated so small dips show.");
  caption.push(teff ? `Colours follow temperature on a stellar colour scale, saturated so the differences show; the star's is its catalogue value (${fmtInt(teff)} K).` : "Colours are illustrative.");
  if (geo.ok) caption.push("The companion's colour, sizes and orbit shape are estimates from the eclipse depths, duration and timing, assuming central eclipses and spherical stars - good to perhaps tens of percent.");
  caption.push("Only the relative orbit is shown; both stars really circle their common centre of mass.");
  caption.push(`Animated about ${speed}x faster than real on average, slowing down through each eclipse, and starting from where the system is in its orbit right now. Hover to pause.`);

  return (
    <div className={className}>
      <svg viewBox="0 0 320 160" className="block w-full" role="img" aria-label="Animated drawing of the two stars and their orbit" onMouseEnter={() => { pausedRef.current = true; }} onMouseLeave={() => { pausedRef.current = false; }}>
        {SPECKS.map(([x, y, s, col], i) => (
          <circle key={i} cx={x} cy={y} r={s} fill={col} opacity={0.4} className="sv-twinkle" style={{ animationDelay: `${i * 0.37}s` }} />
        ))}
        <path d={orbitPaths.back} fill="none" stroke="currentColor" strokeOpacity={0.22} strokeDasharray="2 5" />
        {!front && companion}
        <StarBody cx={CX} cy={CY} r={r1(R1)} color={starColor} edge={starEdge} glow={glow1} flare={!trueScale} texture={!trueScale} radiance={radiance} />
        <path d={orbitPaths.front} fill="none" stroke="currentColor" strokeOpacity={0.32} strokeDasharray="2 5" />
        {front && companion}
      </svg>
      {sortedCurve && (
        <div className="mt-2">
          <svg viewBox="0 0 320 48" className="block w-full" role="img" aria-label="The star's light curve, with the current orbital phase marked">
            <path d={curvePath} fill="none" stroke="currentColor" strokeOpacity={0.5} strokeWidth={1.1} strokeLinejoin="round" />
            <line x1={markerX} x2={markerX} y1={1} y2={47} className="stroke-accent" strokeOpacity={0.6} strokeWidth={1} />
            <circle cx={markerX} cy={markerY} r={2.6} className="fill-accent" />
          </svg>
          <div className="mt-1 flex justify-between font-mono text-[10px] text-muted">
            <span>{stateLabel}</span>
            <span>total light {fRel.toFixed(3)}</span>
          </div>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-panel-2">
            <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.round(Math.min(1, Math.max(0, fRel)) * 1000) / 10}%` }} />
          </div>
        </div>
      )}
      {geo.aR1 !== null && (
        <div className="mt-2 flex justify-center gap-1.5">
          <button type="button" onClick={() => setMode("zoom")} className={`nav-caps rounded-md border px-2.5 py-1 font-mono text-[10px] transition-colors ${mode === "zoom" ? "border-accent text-accent" : "border-line text-muted hover:text-fg"}`}>Zoomed</button>
          <button type="button" onClick={() => setMode("true")} className={`nav-caps rounded-md border px-2.5 py-1 font-mono text-[10px] transition-colors ${mode === "true" ? "border-accent text-accent" : "border-line text-muted hover:text-fg"}`}>True scale</button>
        </div>
      )}
      {geo.note && <p className="mt-3 rounded-md border border-accent-cool/30 bg-accent-cool/5 px-3 py-2 text-[11px] leading-relaxed text-muted">{geo.note}</p>}
      {rows.length > 0 && (
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 font-mono text-[10px] sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 border-b border-line pb-1">
              <dt className="text-faint">{label}</dt>
              <dd className="text-right text-fg">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-2 text-center text-[10px] leading-relaxed text-faint">{caption.join(" ")}</p>
    </div>
  );
}
