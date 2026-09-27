"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { FunnelStep } from "@/lib/types";

// Six real stage counts from the pipeline's own funnel export - no per-star
// identity is available yet (that would need a per-target fate export this
// pipeline does not produce today), so this shows honest AGGREGATE
// attrition: how many candidates remain after each stage, not which
// specific stars died where. The seeded point cloud represents that count;
// it is not a map of real positions or a real per-star outcome.

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const REASONS = ["no usable data", "rejected", "already known", "contaminated", "not confirmed"];
const MAX_POINTS = 520;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

export default function Gauntlet({
  funnel,
  short,
}: {
  funnel: FunnelStep[];
  short: Record<string, string>;
}) {
  const steps = funnel.slice(0, 6);
  const total = steps[0]?.count ?? 0;

  const points = useMemo(() => {
    const r = rng(20260927);
    const maxR = 0.46;
    return Array.from({ length: MAX_POINTS }, (_, i) => {
      const rad = maxR * Math.sqrt((i + 0.5) / MAX_POINTS);
      const theta = i * GOLDEN_ANGLE + r() * 0.3;
      return {
        x: 0.5 + rad * Math.cos(theta),
        y: 0.5 + rad * Math.sin(theta),
        size: 0.6 + r() * 1.6,
      };
    });
  }, []);

  const [stage, setStage] = useState(0);
  const [playing, setPlaying] = useState(true);
  const resumeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderCountRef = useRef(MAX_POINTS);
  const rafRef = useRef<number | null>(null);

  const reducedMotion = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  useEffect(() => {
    if (!playing || reducedMotion) return;
    const id = setInterval(() => setStage((s) => (s + 1) % steps.length), 1800);
    return () => clearInterval(id);
  }, [playing, reducedMotion, steps.length]);

  useEffect(() => {
    if (reducedMotion) setStage(steps.length - 1);
  }, [reducedMotion, steps.length]);

  function selectStage(i: number) {
    setStage(i);
    setPlaying(false);
    if (resumeTimer.current) clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => setPlaying(true), 7000);
  }

  const targetCount =
    total > 0 ? Math.max(1, Math.round((MAX_POINTS * (steps[stage]?.count ?? 0)) / total)) : 0;

  useEffect(() => {
    function frame() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const size = canvas.clientWidth;
      if (size === 0) return;
      canvas.width = Math.round(size * dpr);
      canvas.height = Math.round(size * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      const current = renderCountRef.current;
      const next = current + (targetCount - current) * 0.12;
      renderCountRef.current = Math.abs(next - targetCount) < 0.5 ? targetCount : next;

      const style = getComputedStyle(canvas);
      const faint = style.getPropertyValue("--faint").trim() || "#5f6579";
      const accent = style.getPropertyValue("--accent").trim() || "#93b9ff";
      const t = steps.length > 1 ? stage / (steps.length - 1) : 0;
      const col = mix(faint, accent, t);

      const shown = Math.ceil(renderCountRef.current);
      const frac = renderCountRef.current - Math.floor(renderCountRef.current);
      for (let i = 0; i < points.length && i < shown; i++) {
        const p = points[i];
        const op = i === Math.floor(renderCountRef.current) ? frac : 1;
        ctx.fillStyle = col;
        ctx.globalAlpha = 0.25 + 0.65 * op;
        ctx.beginPath();
        ctx.arc(p.x * size, p.y * size, p.size * (size / 340), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (Math.abs(renderCountRef.current - targetCount) > 0.5) {
        rafRef.current = requestAnimationFrame(frame);
      }
    }
    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [targetCount, stage, points, steps.length]);

  if (steps.length === 0) return null;

  const s = steps[stage];
  const prev = stage > 0 ? steps[stage - 1] : null;
  const dropped = prev ? prev.count - s.count : 0;
  const reason = stage > 0 ? REASONS[stage - 1] : null;

  return (
    <section className="rounded-xl border border-line bg-panel p-4 sm:p-6">
      <div className="nav-caps text-xs text-accent">II. The gauntlet</div>
      <h2 className="mt-1 font-display text-3xl italic text-fg sm:text-4xl">
        Every candidate faces a series of tests. Most do not survive.
      </h2>
      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,20rem)_1fr]">
        <div className="mx-auto aspect-square w-full max-w-xs">
          <canvas ref={canvasRef} className="h-full w-full" />
        </div>
        <div className="flex flex-col justify-center">
          <div className="flex flex-wrap items-center gap-2">
            {steps.map((st, i) => (
              <button
                key={st.label}
                type="button"
                onClick={() => selectStage(i)}
                className={`rounded-md border px-2.5 py-1 font-mono text-xs transition-colors ${
                  i === stage ? "border-accent text-accent" : "border-line text-muted hover:text-fg"
                }`}
              >
                {String(i + 1).padStart(2, "0")}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              className="ml-2 rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:text-fg"
            >
              {playing ? "Pause" : "Play"}
            </button>
          </div>
          <div className="mt-4 font-mono text-4xl text-fg">{s.count.toLocaleString("en-US")}</div>
          <div className="text-sm text-muted">{short[s.label] ?? s.label}</div>
          {reason && dropped > 0 && (
            <div className="mt-1 font-mono text-xs text-rose-300/80">
              -{dropped.toLocaleString("en-US")} {reason}
            </div>
          )}
          <p className="mt-4 max-w-md text-sm text-muted">
            From {total.toLocaleString("en-US")} eclipse-like signals to{" "}
            {steps[steps.length - 1].count.toLocaleString("en-US")} confirmed on-target stars - each
            stage removes noise, contamination, and false positives.
          </p>
        </div>
      </div>
    </section>
  );
}

function mix(a: string, b: string, t: number): string {
  const pa = hex(a);
  const pb = hex(b);
  if (!pa || !pb) return a;
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * Math.max(0, Math.min(1, t))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function hex(v: string): [number, number, number] | null {
  const m = v.trim().match(/^#([0-9a-f]{6})$/i);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
