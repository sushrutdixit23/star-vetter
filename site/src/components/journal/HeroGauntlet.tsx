"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { FunnelStep } from "@/lib/types";
import Band from "./Band";

// Section I (the hero) and section II (the gauntlet), sharing one state.
// Every dot stands for a share of the targets examined, drawn to scale
// from the pipeline's own funnel counts and grouped by the stage where it
// was eliminated - survivors at the core. The row of mini clouds in
// section II is the control: each one shows what survives to that stage,
// and clicking it drives the big galaxy. Group SIZES are exact; dot
// POSITIONS are a fixed decorative spiral, not real sky positions and not
// a per-star record (the pipeline exports aggregate counts per stage).

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const MAX_DOTS = 1100;
const REASONS = [
  "had no usable light curve",
  "failed statistical vetting",
  "were already in a catalog",
  "were traced to a variable neighbour",
  "failed the pixel check",
];

interface Group {
  key: string;
  label: string;
  reached: number;
  count: number;
  color: string;
}

interface Dot {
  x: number;
  y: number;
  size: number;
  group: number;
  reached: number;
}

const fmt = (n: number) => n.toLocaleString("en-US");

function cssColor(c: string): string {
  return c.startsWith("--") ? `var(${c})` : c;
}

function resolveColor(style: CSSStyleDeclaration, c: string): string {
  if (!c.startsWith("--")) return c;
  return style.getPropertyValue(c).trim() || "#9a9fb0";
}

function MiniCloud({ dots, colors, k }: { dots: Dot[]; colors: string[] | null; k: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !colors) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const cv: HTMLCanvasElement = canvas;
    const ctx: CanvasRenderingContext2D = context;
    const palette: string[] = colors;
    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (w === 0 || h === 0) return;
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const size = Math.min(w, h);
      const ox = (w - size) / 2;
      const oy = (h - size) / 2;
      for (const p of dots) {
        if (p.reached < k) continue;
        ctx.globalAlpha = p.group === 0 ? 1 : 0.8;
        ctx.fillStyle = palette[p.group];
        ctx.beginPath();
        ctx.arc(ox + p.x * size, oy + p.y * size, Math.max(0.55, p.size * (size / 300)), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(cv);
    return () => ro.disconnect();
  }, [dots, colors, k]);
  return <canvas ref={ref} aria-hidden="true" className="h-full w-full" />;
}

export default function HeroGauntlet({ funnel, short, intro }: { funnel: FunnelStep[]; short: Record<string, string>; intro: ReactNode }) {
  const steps = useMemo(() => funnel.slice(0, 6), [funnel]);
  const ready = steps.length === 6;

  const groups = useMemo<Group[]>(() => {
    if (steps.length < 6) return [];
    const [S, U, V, N, X, C] = steps.map((s) => s.count);
    return [
      { key: "confirmed", label: "Confirmed on-target", reached: 5, count: C, color: "--fg" },
      { key: "pixel", label: "Failed pixel check", reached: 4, count: Math.max(X - C, 0), color: "--accent-kill" },
      { key: "neighbour", label: "Variable neighbour", reached: 3, count: Math.max(N - X, 0), color: "#c9c4b8" },
      { key: "catalogued", label: "Already catalogued", reached: 2, count: Math.max(V - N, 0), color: "--accent-cool" },
      { key: "vetting", label: "Failed vetting", reached: 1, count: Math.max(U - V, 0), color: "--accent" },
      { key: "nodata", label: "No usable data", reached: 0, count: Math.max(S - U, 0), color: "--faint" },
    ];
  }, [steps]);

  const { dots, perDot } = useMemo(() => {
    const total = groups.reduce((a, g) => a + g.count, 0);
    if (total === 0) return { dots: [] as Dot[], perDot: 1 };
    const scale = MAX_DOTS / total;
    const counts = groups.map((g) => (g.count === 0 ? 0 : Math.max(1, Math.round(g.count * scale))));
    const n = counts.reduce((a, b) => a + b, 0);
    const r = rng(20260927);
    const out: Dot[] = [];
    let i = 0;
    groups.forEach((g, gi) => {
      for (let k = 0; k < counts[gi]; k++) {
        const rad = 0.47 * Math.sqrt((i + 0.5) / n);
        const theta = i * GOLDEN_ANGLE + r() * 0.35;
        out.push({ x: 0.5 + rad * Math.cos(theta), y: 0.5 + rad * Math.sin(theta), size: 0.55 + r() * 1.45, group: gi, reached: g.reached });
        i++;
      }
    });
    return { dots: out, perDot: Math.max(1, Math.round(total / n)) };
  }, [groups]);

  const [stage, setStage] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [colors, setColors] = useState<string[] | null>(null);
  const resumeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const alphaRef = useRef<number[]>([]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setPlaying(false);
      setStage(5);
    }
    return () => {
      if (resumeTimer.current) clearTimeout(resumeTimer.current);
    };
  }, []);

  useEffect(() => {
    const style = getComputedStyle(document.documentElement);
    setColors(groups.map((g) => resolveColor(style, g.color)));
  }, [groups]);

  useEffect(() => {
    if (!playing || !ready) return;
    const id = setTimeout(() => setStage((s) => (s + 1) % 6), stage === 5 ? 4200 : 2000);
    return () => clearTimeout(id);
  }, [playing, ready, stage]);

  function select(i: number) {
    setStage(i);
    setPlaying(false);
    if (resumeTimer.current) clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => setPlaying(true), 8000);
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const cv: HTMLCanvasElement = canvas;
    const ctx: CanvasRenderingContext2D = context;
    if (alphaRef.current.length !== dots.length) alphaRef.current = dots.map(() => 0.9);
    const alphas = alphaRef.current;
    const style = getComputedStyle(cv);
    const palette = groups.map((g) => resolveColor(style, g.color));
    let raf = 0;

    const draw = (): boolean => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (w === 0 || h === 0) return false;
      const pw = Math.round(w * dpr);
      const ph = Math.round(h * dpr);
      if (cv.width !== pw) cv.width = pw;
      if (cv.height !== ph) cv.height = ph;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const size = Math.min(w, h);
      const ox = (w - size) / 2;
      const oy = (h - size) / 2;
      let moving = false;
      for (let i = 0; i < dots.length; i++) {
        const p = dots[i];
        const alive = p.reached >= stage;
        const target = alive ? 0.92 : 0.12;
        const a = alphas[i] + (target - alphas[i]) * 0.1;
        alphas[i] = Math.abs(target - a) < 0.004 ? target : a;
        if (alphas[i] !== target) moving = true;
        const cx = ox + p.x * size;
        const cy = oy + p.y * size;
        const rad = p.size * (size / 360) * (alive ? 1 : 0.8);
        const col = palette[p.group];
        if (p.group === 0) {
          const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad * 3.4);
          g.addColorStop(0, col);
          g.addColorStop(1, "rgba(255,255,255,0)");
          ctx.globalAlpha = alphas[i] * (stage === 5 ? 0.85 : 0.45);
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(cx, cy, rad * 3.4, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = alphas[i];
        ctx.fillStyle = col;
        ctx.beginPath();
        ctx.arc(cx, cy, rad, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      return moving;
    };

    const tick = () => {
      if (draw()) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const ro = new ResizeObserver(() => {
      draw();
    });
    ro.observe(cv);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [stage, dots, groups]);

  const cur = ready ? steps[stage] : null;
  const total = ready ? steps[0].count : 0;
  let caption = "";
  if (cur) {
    if (stage === 0) {
      caption = `Every dot is a share of the ${fmt(total)} targets examined. Pick a stage, or let it play.`;
    } else {
      const dropped = steps[stage - 1].count - cur.count;
      caption = `${fmt(dropped)} ${REASONS[stage - 1]}. `;
      caption += stage === 5 ? `${fmt(cur.count)} survive every test - ${((100 * cur.count) / total).toFixed(1)}% of everything examined.` : `${fmt(cur.count)} remain.`;
    }
  }

  return (
    <>
      <section className="py-10 sm:py-14">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] xl:grid-cols-[3rem_minmax(0,26rem)_minmax(0,1fr)_13rem]">
          <div className="hidden font-display text-3xl leading-none text-faint xl:block">I</div>
          <div className="flex flex-col justify-center">{intro}</div>
          {ready && (
            <div className="aspect-[4/3] max-h-[78vh] w-full">
              <canvas ref={canvasRef} aria-hidden="true" className="h-full w-full" />
            </div>
          )}
          {ready && (
            <aside className="self-center lg:col-span-2 xl:col-span-1">
              <div className="nav-caps font-mono text-[11px] text-fg">The fate galaxy</div>
              <div className="mt-1 font-mono text-[10px] text-faint">{fmt(total)} targets examined</div>
              <ul className="mt-4 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3 xl:grid-cols-1">
                {groups.filter((g) => g.count > 0).map((g) => {
                  const out = g.reached < stage;
                  const justOut = g.reached === stage - 1;
                  return (
                    <li key={g.key} className={`flex items-center gap-2 transition-opacity ${out && !justOut ? "opacity-40" : ""} ${justOut ? "text-fg" : "text-muted"}`}>
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: cssColor(g.color) }} />
                      <span>{g.label}</span>
                      <span className="ml-auto font-mono text-faint">{fmt(g.count)}</span>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-4 border-t border-line pt-3 text-[10px] leading-relaxed text-faint">Each dot is about {perDot} targets, coloured by where it was eliminated. Group sizes are exact; positions are illustrative, not real sky positions.</p>
            </aside>
          )}
        </div>
      </section>

      {ready && (
        <Band num="II" title="The gauntlet" lede="Every candidate faces a series of tests. Most do not survive." action={<button type="button" onClick={() => setPlaying((p) => !p)} className="nav-caps rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-muted hover:text-fg">{playing ? "Pause" : "Play"}</button>}>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_16rem]">
            <ol className="grid grid-cols-3 gap-3 sm:grid-cols-6">
              {steps.map((st, i) => (
                <li key={st.label}>
                  <button type="button" onClick={() => select(i)} aria-pressed={i === stage} className={`w-full rounded-lg border p-2 text-center transition-colors ${i === stage ? "border-accent/70 bg-accent/5" : "border-transparent hover:border-line"}`}>
                    <div className="font-display text-2xl text-fg">{fmt(st.count)}</div>
                    <div className="nav-caps mt-0.5 font-mono text-[9px] leading-tight text-muted">{short[st.label] ?? st.label}</div>
                    <div className="mx-auto mt-2 aspect-square w-full max-w-[7rem]">
                      <MiniCloud dots={dots} colors={colors} k={i} />
                    </div>
                  </button>
                </li>
              ))}
            </ol>
            <div className="flex flex-col justify-center xl:border-l xl:border-line xl:pl-6">
              <p className="text-sm leading-relaxed text-muted" aria-live="polite">{caption}</p>
              <Link href="/about" className="nav-caps mt-4 inline-flex w-fit items-center rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg hover:border-accent/60">See how it works &rarr;</Link>
            </div>
          </div>
        </Band>
      )}
    </>
  );
}
