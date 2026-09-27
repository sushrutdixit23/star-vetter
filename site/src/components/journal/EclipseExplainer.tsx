"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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

export default function EclipseExplainer() {
  const reducedMotion = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );
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
        setPhase((p) => (p + dt / 8) % 1);
      }
      lastRef.current = t;
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing]);

  const f = flux(phase);
  const label =
    phase < 0.06 || phase > 0.94
      ? "Primary eclipse"
      : phase > 0.44 && phase < 0.56
        ? "Secondary eclipse"
        : "Both visible";

  const angle = phase * 2 * Math.PI;
  const orbitRx = 120;
  const orbitRy = 32;
  const secX = 160 + orbitRx * Math.sin(angle);
  const secY = 80 + orbitRy * Math.cos(angle);
  const inFront = Math.sin(angle) > 0 ? phase < 0.5 : phase >= 0.5;

  function onScrub(v: number) {
    setPlaying(false);
    setPhase(((v % 1) + 1) % 1);
  }

  const shownPhase = phase > 0.5 ? phase - 1 : phase;

  return (
    <section className="rounded-xl border border-line bg-panel p-4 sm:p-6">
      <div className="nav-caps text-xs text-accent">III. An eclipse, explained</div>
      <h2 className="mt-1 font-display text-3xl italic text-fg sm:text-4xl">
        Two stars, one repeating shadow.
      </h2>
      <p className="mt-2 max-w-xl text-sm text-muted">
        When two stars orbit edge-on to us, each blocks the other once per orbit. A telescope sees
        their combined light dip twice, on a precise clock.
      </p>
      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div>
          <svg viewBox="0 0 320 160" className="w-full text-fg">
            <ellipse
              cx="160"
              cy="80"
              rx={orbitRx}
              ry={orbitRy}
              fill="none"
              stroke="currentColor"
              strokeOpacity="0.25"
              strokeDasharray="2 6"
            />
            {inFront ? (
              <>
                <circle cx="160" cy="80" r="26" className="fill-accent" />
                <circle cx={secX} cy={secY} r="13" className="fill-accent-cool" />
              </>
            ) : (
              <>
                <circle cx={secX} cy={secY} r="13" className="fill-accent-cool" />
                <circle cx="160" cy="80" r="26" className="fill-accent" />
              </>
            )}
          </svg>
          <div className="mt-1 flex justify-center gap-6 text-[11px]">
            <span className={`nav-caps ${label === "Primary eclipse" ? "text-accent" : "text-faint"}`}>
              Primary eclipse
            </span>
            <span className={`nav-caps ${label === "Both visible" ? "text-fg" : "text-faint"}`}>
              Both visible
            </span>
            <span className={`nav-caps ${label === "Secondary eclipse" ? "text-accent-cool" : "text-faint"}`}>
              Secondary eclipse
            </span>
          </div>
        </div>
        <div>
          <svg viewBox="0 0 320 120" className="w-full">
            <line x1="0" y1="20" x2="320" y2="20" className="stroke-line" strokeWidth={1} />
            <path
              d={CURVE.map(
                (p, i) => `${i === 0 ? "M" : "L"} ${(p.phase + 0.5) * 320} ${20 + (1 - p.flux) * 380}`
              ).join(" ")}
              fill="none"
              className="stroke-fg"
              strokeWidth={1.5}
            />
            <line
              x1={(shownPhase + 0.5) * 320}
              x2={(shownPhase + 0.5) * 320}
              y1={0}
              y2={120}
              className="stroke-accent"
              strokeOpacity={0.5}
            />
          </svg>
          <div className="mt-1 flex items-center justify-between text-[11px] text-muted">
            <span>Stellar brightness</span>
            <span className="font-mono text-fg">{f.toFixed(3)}</span>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              className="rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:text-fg"
            >
              {playing ? "Pause" : "Play"}
            </button>
            <input
              type="range"
              min={0}
              max={0.999}
              step={0.001}
              value={phase}
              onChange={(e) => onScrub(Number(e.target.value))}
              className="flex-1 accent-accent"
            />
          </div>
        </div>
      </div>
      <p className="mt-4 text-[11px] text-faint">
        Illustration of the general eclipsing-binary pattern - not measured data for any specific
        star. Every real light curve on this site plots its primary eclipse at phase 0, the same
        convention shown here.
      </p>
    </section>
  );
}
