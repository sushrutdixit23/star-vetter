"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { CursorOverlay, EclipseWindow, eclipseCentres, fluxRange } from "./charts";
import { eclipseState, interp, outline, skyPosition, wrapPhase } from "@/lib/orbit";
import type { StudioStar } from "@/lib/physicsTypes";
import type { Quantile } from "@/lib/types";

const ORBIT_SECONDS = 15;
const HOT = [255, 238, 208];
const COOL = [255, 138, 76];

function mix(a: number[], b: number[], t: number): number[] {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t));
}
const rgb = (c: number[]) => `rgb(${c[0]},${c[1]},${c[2]})`;

// Schematic colours: the fitted surface-brightness ratio says which star is cooler, nothing more.
function starColours(J: number) {
  const t = Math.min(1, Math.max(0, Math.min(J, 1 / J)));
  const cool = mix(COOL, HOT, Math.pow(t, 0.7));
  return J >= 1 ? { c1: cool, c2: HOT } : { c1: HOT, c2: cool };
}

function q(x: Quantile | null | undefined, d = 3): string {
  if (!x) return "n/a";
  const dd = x.hi < 0.001 && x.lo < 0.001 ? d + 1 : d;
  return `${x.median.toFixed(dd)} +${x.hi.toFixed(dd)}/-${x.lo.toFixed(dd)}`;
}

const wrapDelta = (x: number) => x - Math.round(x);
const rd = (v: number) => Math.round(v * 100) / 100;

// Browser-only inputs read through useSyncExternalStore so the server render and first paint agree.
function subscribeHash(cb: () => void) {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}
function readHashTic(): number {
  const m = window.location.hash.match(/^#tic-(\d+)$/);
  return m ? Number(m[1]) : 0;
}
function subscribeMotion(cb: () => void) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}
const readReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function Disc({ id, c, cx, cy, r }: { id: string; c: number[]; cx: number; cy: number; r: number }) {
  return (
    <g>
      <defs>
        <radialGradient id={id} cx="42%" cy="40%" r="70%">
          <stop offset="0%" stopColor={rgb(mix(c, [255, 255, 255], 0.35))} />
          <stop offset="65%" stopColor={rgb(c)} />
          <stop offset="100%" stopColor={rgb(c.map((v) => Math.round(v * 0.5)))} />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={r + 5} fill={rgb(c)} opacity="0.1" />
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id})`} stroke="rgba(7,9,15,0.6)" strokeWidth="1.2" />
    </g>
  );
}

export default function OrbitStudio({ stars, initialTic }: { stars: StudioStar[]; initialTic: number }) {
  const hashTic = useSyncExternalStore(subscribeHash, readHashTic, () => 0);
  const reduced = useSyncExternalStore(subscribeMotion, readReducedMotion, () => true);
  const [picked, setPicked] = useState<number | null>(null);
  const [userPlay, setUserPlay] = useState<boolean | null>(null);
  const [phase, setPhase] = useState(-0.02);
  const [linger, setLinger] = useState(true);
  const tic = picked ?? (stars.some((s) => s.tic === hashTic) ? hashTic : initialTic);
  const playing = userPlay ?? !reduced;
  const star = stars.find((s) => s.tic === tic) ?? stars[0];
  const curve = star.curve;
  const fit = star.fit;
  const trusted = !!fit.e_reliable;

  const centres = useMemo(() => eclipseCentres(curve), [curve]);
  const [yMin, yMax] = useMemo(() => fluxRange(curve), [curve]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const dur = curve.duration_phase;
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      setPhase((p) => {
        let f = 1;
        if (linger) {
          const d = Math.min(Math.abs(wrapDelta(p)), Math.abs(wrapDelta(p - centres.secondary)));
          const s = Math.min(1, d / (2.6 * dur));
          f = 0.28 + 0.72 * s * s * (3 - 2 * s);
        }
        return wrapPhase(p + (dt / ORBIT_SECONDS) * f);
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, linger, curve, centres]);

  const select = (t: number) => {
    setPicked(t);
    setPhase(-0.02);
    try {
      window.history.replaceState(null, "", `#tic-${t}`);
    } catch {
      /* hash is a convenience only */
    }
  };

  const g = useMemo(() => {
    const bf = curve.best_fit;
    const e = bf.e;
    const w = (bf.omega_deg * Math.PI) / 180;
    const r1 = bf.rsum / (1 + bf.k);
    const r2 = bf.rsum - r1;
    const o = outline(e, w, bf.incl, 240);
    const xs = o.sky.map((p) => p[0]);
    const ys = o.sky.map((p) => p[1]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const rmax = Math.max(r1, r2);
    const W = 960, WO = 650, padX = 36, padY = 34;
    let S = (WO - 2 * padX) / (xmax - xmin + 2 * rmax);
    let H = Math.round(S * (ymax - ymin + 2 * rmax) + 2 * padY);
    H = Math.max(260, Math.min(360, H));
    S = Math.min(S, (H - 2 * padY) / (ymax - ymin + 2 * rmax));
    const ox = WO / 2 - (S * (xmin + xmax)) / 2;
    const oy = H / 2 + (S * (ymin + ymax)) / 2;
    const ZC = { x: 810, y: H / 2 + 8 };
    const ZP = Math.min(128, H / 2 - 34);
    const SZ = ZP / (1.5 * (r1 + r2));
    const px = o.plane.map((p) => p[0]), py = o.plane.map((p) => p[1]);
    const pxmin = Math.min(...px), pxmax = Math.max(...px), pymin = Math.min(...py), pymax = Math.max(...py);
    const T = 240, tpadX = 30, tpadT = 40, tpadB = 22;
    const S2 = Math.min((T - 2 * tpadX) / (pxmax - pxmin), (T - tpadT - tpadB) / (pymax - pymin));
    const ox2 = T / 2 - (S2 * (pxmin + pxmax)) / 2;
    const oy2 = tpadT + (T - tpadT - tpadB) / 2 + (S2 * (pymin + pymax)) / 2;
    return { e, w, r1, r2, o, S, W, WO, H, ox, oy, ZC, ZP, SZ, S2, ox2, oy2, T, incl: bf.incl, J: bf.J, cols: starColours(bf.J) };
  }, [curve]);

  const pos = skyPosition(phase, g.e, g.w, g.incl);
  const state = eclipseState(pos, g.r1, g.r2);
  const flux = interp(curve.model.x, curve.model.y, phase, 1);
  const starFront = pos.z > 0;
  const R1 = rd(Math.max(g.r1 * g.S, 3));
  const R2 = rd(Math.max(g.r2 * g.S, 3));
  const c1 = { x: rd(g.ox), y: rd(g.oy) };
  const c2 = { x: rd(g.ox + g.S * pos.x), y: rd(g.oy - g.S * pos.y) };
  let zx = g.SZ * pos.x;
  let zy = -g.SZ * pos.y;
  const zk = Math.max(Math.abs(zx), Math.abs(zy)) / (g.ZP - 9);
  const zFar = zk > 1;
  if (zFar) {
    zx /= zk;
    zy /= zk;
  }
  const z1 = { x: g.ZC.x, y: g.ZC.y };
  const z2 = { x: rd(g.ZC.x + zx), y: rd(g.ZC.y + zy) };
  const Z1 = rd(g.r1 * g.SZ);
  const Z2 = rd(g.r2 * g.SZ);
  const t1 = { x: rd(g.ox2), y: rd(g.oy2) };
  const t2 = { x: rd(g.ox2 + g.S2 * pos.r * Math.cos(pos.u)), y: rd(g.oy2 - g.S2 * pos.r * Math.sin(pos.u)) };
  const peri = { x: rd(g.ox2 + g.S2 * (1 - g.e) * Math.cos(g.w)), y: rd(g.oy2 - g.S2 * (1 - g.e) * Math.sin(g.w)) };
  const skyPath = g.o.sky.map((p, i) => `${i ? "L" : "M"}${(g.ox + g.S * p[0]).toFixed(1)} ${(g.oy - g.S * p[1]).toFixed(1)}`).join("");
  const planePath = g.o.plane.map((p, i) => `${i ? "L" : "M"}${(g.ox2 + g.S2 * p[0]).toFixed(1)} ${(g.oy2 - g.S2 * p[1]).toFixed(1)}`).join("");
  const ribbonX = (ph: number) => rd(12 + ((ph + 0.25) / 1) * 936);
  const ribbon = curve.model.x.map((x, i) => `${i ? "L" : "M"}${ribbonX(x).toFixed(1)} ${(8 + (1 - Math.min(1, Math.max(0, (curve.model.y[i] - curve.min_flux) / (1 - curve.min_flux + 1e-9)))) * 30).toFixed(1)}`).join("");
  const stateText = state === "primary" ? "Primary eclipse: star 2 passes in front of star 1" : state === "secondary" ? "Secondary eclipse: star 1 passes in front of star 2" : "Out of eclipse";
  const sortedStars = useMemo(() => [...stars].sort((a, b) => a.curve.period_days - b.curve.period_days), [stars]);
  const gaia = star.gaia;

  return (
    <div className="mt-6">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Choose a star">
        {sortedStars.map((s) => {
          const on = s.tic === tic;
          const ok = !!s.fit.e_reliable;
          return (
            <button
              key={s.tic}
              type="button"
              aria-pressed={on}
              onClick={() => select(s.tic)}
              className={`rounded-md border px-3 py-2 text-left font-mono text-[11px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${on ? "border-accent bg-panel-2 text-fg" : "border-line text-muted hover:border-accent/60 hover:text-fg"}`}
            >
              <span className="flex items-center gap-2">
                <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full border ${ok ? "border-accent bg-accent" : "border-muted"}`} />
                TIC {s.tic}
              </span>
              <span className="mt-0.5 block text-faint">
                {s.curve.period_days.toFixed(2)} d{ok ? ` \u00b7 e ${s.curve.best_fit.e.toFixed(2)}` : " \u00b7 e cos \u03c9 only"}
              </span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-faint">
        <span aria-hidden="true" className="mr-1 inline-block h-2 w-2 rounded-full border border-accent bg-accent align-baseline" />filled: the eccentricity passes the trust rules.
        <span aria-hidden="true" className="ml-3 mr-1 inline-block h-2 w-2 rounded-full border border-muted align-baseline" />hollow: only e cos &omega; is trusted.
      </p>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="min-w-0">
          <div className="rounded-xl border border-line bg-panel">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
              <span className="font-mono text-[11px] text-muted">As Earth sees it &middot; TIC {star.tic}</span>
              <span className={`font-mono text-[11px] ${state === "none" ? "text-faint" : "text-accent-cool"}`}>{stateText}</span>
            </div>
            <svg
              viewBox={`0 0 ${g.W} ${g.H + 22}`}
              className="block h-auto w-full"
              role="img"
              aria-label={`The two stars of TIC ${star.tic} drawn to scale as seen from Earth, with star 2's projected orbit. ${stateText}.`}
            >
              <path d={skyPath} fill="none" className={trusted ? "stroke-line" : "stroke-faint"} strokeWidth="1.2" strokeDasharray={trusted ? undefined : "4 5"} />
              {starFront ? (
                <>
                  <Disc id={`s1-${star.tic}`} c={g.cols.c1} cx={c1.x} cy={c1.y} r={R1} />
                  <Disc id={`s2-${star.tic}`} c={g.cols.c2} cx={c2.x} cy={c2.y} r={R2} />
                </>
              ) : (
                <>
                  <Disc id={`s2-${star.tic}`} c={g.cols.c2} cx={c2.x} cy={c2.y} r={R2} />
                  <Disc id={`s1-${star.tic}`} c={g.cols.c1} cx={c1.x} cy={c1.y} r={R1} />
                </>
              )}
              <text x={c1.x} y={c1.y + R1 + 15} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily="var(--font-geist-mono)">1</text>
              <text x={c2.x} y={c2.y + R2 + 15} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily="var(--font-geist-mono)">2</text>
              <text x={16} y={g.H - 12} className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">radii and orbit to scale; colours schematic</text>
              <line x1={g.WO + 10} x2={g.WO + 10} y1={16} y2={g.H - 16} className="stroke-line" />
              <text x={g.ZC.x} y={22} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">close-up of the eclipse</text>
              <clipPath id={`zoom-${star.tic}`}><rect x={g.ZC.x - g.ZP} y={g.ZC.y - g.ZP} width={2 * g.ZP} height={2 * g.ZP} rx="6" /></clipPath>
              <rect x={g.ZC.x - g.ZP} y={g.ZC.y - g.ZP} width={2 * g.ZP} height={2 * g.ZP} rx="6" fill="none" className="stroke-line" />
              <g clipPath={`url(#zoom-${star.tic})`}>
                {zFar ? (
                  <Disc id={`z1-${star.tic}`} c={g.cols.c1} cx={z1.x} cy={z1.y} r={Z1} />
                ) : starFront ? (
                  <>
                    <Disc id={`z1-${star.tic}`} c={g.cols.c1} cx={z1.x} cy={z1.y} r={Z1} />
                    <Disc id={`z2-${star.tic}`} c={g.cols.c2} cx={z2.x} cy={z2.y} r={Z2} />
                  </>
                ) : (
                  <>
                    <Disc id={`z2-${star.tic}`} c={g.cols.c2} cx={z2.x} cy={z2.y} r={Z2} />
                    <Disc id={`z1-${star.tic}`} c={g.cols.c1} cx={z1.x} cy={z1.y} r={Z1} />
                  </>
                )}
              </g>
              {zFar ? (
                <g>
                  <circle cx={z2.x} cy={z2.y} r="7" fill="none" className="stroke-muted" strokeWidth="1.5" />
                  <text x={z2.x} y={z2.y + 3.5} textAnchor="middle" className="fill-muted" fontSize="10" fontFamily="var(--font-geist-mono)">2</text>
                </g>
              ) : null}
              <text x={g.ZC.x} y={g.ZC.y + g.ZP + 16} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">{zFar ? "star 2 is outside this window" : "star 2 is in the window"}</text>
            </svg>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {[
              { c: centres.primary, title: "Primary eclipse", label: "deeper eclipse" },
              { c: centres.secondary, title: "Secondary eclipse", label: "shallower eclipse" },
            ].map((w) => (
              <div key={w.title} className="rounded-xl border border-line bg-panel p-3">
                <div className="relative">
                  <EclipseWindow curve={curve} centre={w.c} yMin={yMin} yMax={yMax} title={w.title} label={w.label} />
                  <CursorOverlay curve={curve} centre={w.c} yMin={yMin} yMax={yMax} phase={phase} flux={flux} />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-line bg-panel p-3">
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => setUserPlay(!playing)} className="min-w-20 rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg transition-colors hover:border-accent/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                {playing ? "Pause" : "Play"}
              </button>
              <button type="button" onClick={() => { setUserPlay(false); setPhase(0); }} className="rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-muted transition-colors hover:border-accent/60 hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                Go to primary
              </button>
              <button type="button" onClick={() => { setUserPlay(false); setPhase(wrapPhase(centres.secondary)); }} className="rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-muted transition-colors hover:border-accent/60 hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                Go to secondary
              </button>
              <label className="ml-auto flex items-center gap-2 font-mono text-[11px] text-muted">
                <input type="checkbox" checked={linger} onChange={(e) => setLinger(e.target.checked)} className="accent-[var(--accent)]" />
                Slow down at eclipses
              </label>
            </div>
            <div className="relative mt-3 rounded-md focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
              <svg viewBox="0 0 960 54" className="block h-auto w-full" aria-hidden="true">
                <path d={ribbon} fill="none" className="stroke-accent" strokeWidth="1.6" />
                <line x1={12} x2={948} y1={8} y2={8} className="stroke-line" strokeDasharray="2 4" />
                <text x={ribbonX(0)} y={51} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">primary</text>
                <text x={ribbonX(centres.secondary)} y={51} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">secondary</text>
                <line x1={ribbonX(phase)} x2={ribbonX(phase)} y1={2} y2={42} className="stroke-accent-cool" strokeWidth="2" />
              </svg>
              <input
                type="range"
                min={-0.25}
                max={0.75}
                step={0.001}
                value={phase}
                onPointerDown={() => setUserPlay(false)}
                onChange={(e) => { setUserPlay(false); setPhase(Number(e.target.value)); }}
                aria-label="Orbital phase, 0 is mid-primary-eclipse"
                aria-valuetext={`phase ${phase.toFixed(3)}, flux ${flux.toFixed(4)}`}
                className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
              />
            </div>
            <div className="mt-1 flex flex-wrap justify-between gap-x-4 font-mono text-[11px] text-muted">
              <span>phase {phase.toFixed(3)}</span>
              <span>model flux {flux.toFixed(4)}</span>
              <span>one orbit = {curve.period_days.toFixed(3)} d</span>
            </div>
          </div>
        </div>

        <aside className="min-w-0 rounded-xl border border-line bg-panel p-4">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="font-display text-xl text-fg">TIC {star.tic}</h3>
            <Link href={`/candidates/${star.tic}`} className="sv-link font-mono text-[11px] text-muted hover:text-fg">candidate page</Link>
          </div>
          <svg viewBox={`0 0 ${g.T} ${g.T}`} className="mx-auto mt-2 block h-auto w-full max-w-[240px]" role="img" aria-label="The orbit seen from above: star 2's path around star 1, with the direction to Earth marked at the top.">
            <text x={g.T / 2} y={13} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">to Earth</text>
            <path d={`M${g.T / 2} 18 L${g.T / 2} 30 M${g.T / 2 - 4} 26 L${g.T / 2} 31 L${g.T / 2 + 4} 26`} fill="none" className="stroke-muted" strokeWidth="1.2" />
            <path d={planePath} fill="none" className={trusted ? "stroke-muted" : "stroke-faint"} strokeWidth="1.2" strokeDasharray={trusted ? undefined : "4 5"} />
            {g.e >= 0.05 ? (
              <g>
                <line x1={t1.x} y1={t1.y} x2={peri.x} y2={peri.y} className="stroke-faint" strokeDasharray="2 3" />
                <circle cx={peri.x} cy={peri.y} r="2.6" className="fill-accent-cool" />
                <text x={peri.x + (peri.x > g.T * 0.6 ? -6 : 6)} y={peri.y + (peri.y >= t1.y ? 12 : -5)} textAnchor={peri.x > g.T * 0.6 ? "end" : "start"} className="fill-faint" fontSize="10" fontFamily="var(--font-geist-mono)">periastron</text>
              </g>
            ) : null}
            <line x1={t1.x} y1={t1.y} x2={t2.x} y2={t2.y} className="stroke-line" />
            <circle cx={t1.x} cy={t1.y} r={rd(Math.max(g.r1 * g.S2, 3))} fill={rgb(g.cols.c1)} />
            <circle cx={t2.x} cy={t2.y} r={rd(Math.max(g.r2 * g.S2, 3))} fill={rgb(g.cols.c2)} />
          </svg>
          <p className="mt-1 text-center text-[11px] text-faint">{trusted ? "Orbit seen from above" : "Orbit shape not reliable: dashed"}</p>

          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t border-line pt-4 text-sm">
            <dt className="text-muted">Period</dt>
            <dd className="text-right font-mono text-fg">{curve.period_days.toFixed(4)} d</dd>
            <dt className="text-muted">Eccentricity</dt>
            <dd className="text-right font-mono text-fg">{trusted ? q(fit.e, 3) : <span className="text-faint">not trusted</span>}</dd>
            <dt className="text-muted">e cos &omega;</dt>
            <dd className="text-right font-mono text-fg">{q(fit.ecosw, 4)}</dd>
            {trusted ? (
              <>
                <dt className="text-muted">&omega;</dt>
                <dd className="text-right font-mono text-fg">{fit.omega_deg ? `${fit.omega_deg.median.toFixed(0)}\u00b0` : "n/a"}</dd>
              </>
            ) : null}
            <dt className="text-muted">Inclination</dt>
            <dd className="text-right font-mono text-fg">{q(fit.incl_deg, 2)}&deg;</dd>
            <dt className="text-muted">r1 / r2</dt>
            <dd className="text-right font-mono text-fg">{fit.r1?.median.toFixed(4)} / {fit.r2?.median.toFixed(4)}</dd>
            <dt className="text-muted">Radius ratio</dt>
            <dd className="text-right font-mono text-fg">{fit.k?.median.toFixed(2)}</dd>
            <dt className="text-muted">Third light</dt>
            <dd className="text-right font-mono text-fg">{fit.l3?.median.toFixed(2)}{fit.l3_constrained ? "" : <span className="text-faint"> (prior)</span>}</dd>
            <dt className="text-muted">Fit residual</dt>
            <dd className="text-right font-mono text-fg">{curve.rms_resid_ppt.toFixed(2)} ppt rms</dd>
          </dl>
          <p className="mt-2 text-[11px] leading-relaxed text-faint">Radii are fractions of the orbit&apos;s semi-major axis. Table: posterior medians. Drawing: best-fit solution.</p>

          <ul className="mt-4 space-y-2 border-t border-line pt-4 text-xs leading-relaxed text-muted">
            <li>
              {trusted
                ? "Eccentricity passes the trust rules: stars not too close, secondary eclipse measured on its own, both routes to e cos \u03c9 agree."
                : `Only e cos \u03c9 is trusted here: ${fit.e_note ?? "the full eccentricity failed a trust rule"}.`}
            </li>
            {!fit.converged ? <li>The sampler chain is short, so uncertainties are indicative.</li> : null}
            {gaia ? (
              <li className="text-fg">
                {gaia.same_period
                  ? `Gaia holds a spectroscopic orbit at this period (ratio ${gaia.period_ratio.toFixed(4)}${gaia.k1_kms ? `, K1 ${gaia.k1_kms.toFixed(0)} km/s` : ""}).`
                  : `Gaia holds a ${gaia.period_days.toFixed(0)}-day orbit for the bright star, far longer than the eclipses: a possible third body, unverified.`}
              </li>
            ) : null}
            {star.ecc_check ? (
              <li className="text-fg">
                Gaia e {star.ecc_check.gaia_e.toFixed(3)} &plusmn; {star.ecc_check.gaia_e_sigma.toFixed(3)} against {star.ecc_check.fit_e.toFixed(3)} here: {star.ecc_check.diff_sigma.toFixed(1)} sigma apart{star.ecc_check.trusted ? "." : "; this fit's eccentricity is not trusted."}
              </li>
            ) : null}
            {star.rv ? (
              <li>
                Gaia velocity range {star.rv.range_kms.toFixed(0)} km/s over {star.rv.n_transits} transits:{" "}
                {star.rv.verdict === "moves" ? "the bright star moves." : star.rv.verdict === "blend_indicated" ? "static while the eclipse is deep, so the eclipse likely belongs to another star." : "no clear motion."}
              </li>
            ) : null}
          </ul>
        </aside>
      </div>
    </div>
  );
}
