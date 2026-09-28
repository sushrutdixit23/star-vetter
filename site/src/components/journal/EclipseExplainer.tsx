"use client";

import Link from "next/link";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import Band from "./Band";
import StarBody from "../StarBody";

// A generic, illustrative eclipsing-binary diagram - not measured data for
// any specific star. It teaches the phase convention every real chart on
// this site uses (primary eclipse at phase 0) before a visitor sees any
// actual measurement. Path coordinates are rounded so server and client
// render identical markup.

function flux(phase: number): number {
  let v = 1;
  const dips: [number, number, number][] = [
    [0, 0.22, 0.05],
    [0.5, 0.08, 0.05],
  ];
  for (const [center, depth, hw] of dips) {
    let d = Math.abs(phase - center);
    d = Math.min(d, 1 - d);
    if (d < hw) v -= depth * Math.pow(1 - (d / hw) ** 2, 1.4);
  }
  return v;
}

const CURVE = Array.from({ length: 400 }, (_, i) => {
  const phase = i / 400 - 0.5;
  const wrapped = ((phase % 1) + 1) % 1;
  return { phase, flux: flux(wrapped) };
});

function segment(keep: (ph: number) => boolean): string {
  let d = "";
  let drawing = false;
  for (const p of CURVE) {
    if (!keep(p.phase)) {
      drawing = false;
      continue;
    }
    d += `${drawing ? "L" : "M"} ${((p.phase + 0.5) * 320).toFixed(1)} ${(20 + (1 - p.flux) * 380).toFixed(1)} `;
    drawing = true;
  }
  return d;
}

const FULL = segment(() => true);
const PRIMARY = segment((ph) => Math.abs(ph) < 0.06);
const SECONDARY = segment((ph) => Math.abs(ph) > 0.44);

export default function EclipseExplainer() {
  const uid = useId();
  const reducedMotion = useMemo(() => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches, []);
  const [phase, setPhase] = useState(0);
  const [playing, setPlaying] = useState(!reducedMotion);
  const rafRef = useRef<number | null>(null);
  const lastRef = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      lastRef.current = null;
      return;
    }
    function tick(t: number) {
      if (lastRef.current !== null) {
        const dt = (t - lastRef.current) / 1000;
        setPhase((p) => {
          const next = p + dt / 8;
          return next >= 0.5 ? next - 1 : next;
        });
      }
      lastRef.current = t;
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing]);

  const f = flux(phase < 0 ? phase + 1 : phase);
  const label = Math.abs(phase) < 0.06 ? "Primary eclipse" : Math.abs(phase) > 0.44 ? "Secondary eclipse" : "Both visible";

  const angle = phase * 2 * Math.PI;
  const orbitRx = 120;
  const orbitRy = 12;
  const secX = 160 + orbitRx * Math.sin(angle);
  const secY = 80 + orbitRy * Math.cos(angle);
  const secondaryInFront = Math.cos(angle) > 0;

  function onScrub(v: number) {
    setPlaying(false);
    setPhase(v);
  }

  return (
    <Band variant="half" num="III" title="An eclipse, explained" lede="When two stars orbit edge-on to us, each blocks the other once per orbit. A telescope sees their combined light dip twice, on a precise clock." action={<Link href="/glossary" className="nav-caps inline-flex items-center rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg hover:border-accent/60">Learn more &rarr;</Link>}>
      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <svg viewBox="0 0 320 160" className="w-full text-fg">
            <defs>
              <radialGradient id={`ecl-primary-${uid}`} cx="35%" cy="32%" r="70%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="45%" style={{ stopColor: "var(--accent)" }} />
                <stop offset="100%" style={{ stopColor: "var(--accent)" }} stopOpacity="0.85" />
              </radialGradient>
              <radialGradient id={`ecl-secondary-${uid}`} cx="35%" cy="32%" r="70%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="50%" style={{ stopColor: "var(--accent-cool)" }} />
                <stop offset="100%" style={{ stopColor: "var(--accent-cool)" }} stopOpacity="0.85" />
              </radialGradient>
            </defs>
            <ellipse cx="160" cy="80" rx={orbitRx} ry={orbitRy} fill="none" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="2 6" />
            {secondaryInFront ? (
              <>
                <StarBody cx={160} cy={80} r={26} color="var(--accent)" glow={1.1} flare />
                <StarBody cx={secX} cy={secY} r={13} color="var(--accent-cool)" glow={0.8} texture={false} />
              </>
            ) : (
              <>
                <StarBody cx={secX} cy={secY} r={13} color="var(--accent-cool)" glow={0.8} texture={false} />
                <StarBody cx={160} cy={80} r={26} color="var(--accent)" glow={1.1} flare />
              </>
            )}
          </svg>
          <div className="mt-1 flex justify-center gap-4 font-mono text-[10px]">
            <span className={`nav-caps ${label === "Primary eclipse" ? "text-accent" : "text-faint"}`}>Primary</span>
            <span className={`nav-caps ${label === "Both visible" ? "text-fg" : "text-faint"}`}>Both visible</span>
            <span className={`nav-caps ${label === "Secondary eclipse" ? "text-accent-cool" : "text-faint"}`}>Secondary</span>
          </div>
        </div>
        <div>
          <div className="nav-caps font-mono text-[10px] text-faint">Stellar brightness</div>
          <svg viewBox="0 0 320 120" className="mt-1 w-full">
            <line x1="0" y1="20" x2="320" y2="20" className="stroke-line" strokeWidth={1} />
            <path d={FULL} fill="none" className="stroke-fg" strokeOpacity={0.35} strokeWidth={1.5} />
            <path d={PRIMARY} fill="none" className="stroke-accent" strokeWidth={2} />
            <path d={SECONDARY} fill="none" className="stroke-accent-cool" strokeWidth={2} />
            <line x1={(phase + 0.5) * 320} x2={(phase + 0.5) * 320} y1={0} y2={120} className="stroke-accent" strokeOpacity={0.5} />
          </svg>
          <div className="mt-1 flex items-center justify-between text-[11px] text-muted">
            <span>{label}</span>
            <span className="font-mono text-fg">{f.toFixed(3)}</span>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button type="button" onClick={() => setPlaying((p) => !p)} className="nav-caps rounded-md border border-line px-2.5 py-1 font-mono text-[10px] text-muted hover:text-fg">{playing ? "Pause" : "Play"}</button>
            <input type="range" min={-0.5} max={0.4995} step={0.001} value={phase} onChange={(e) => onScrub(Number(e.target.value))} className="flex-1 accent-accent" aria-label="Orbital phase" />
          </div>
        </div>
      </div>
      <p className="mt-4 text-[11px] text-faint">Illustration of the general pattern, not measured data for any specific star. Every real light curve on this site plots its primary eclipse at phase 0, the same convention used here.</p>
    </Band>
  );
}
