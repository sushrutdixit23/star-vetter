"use client";

import { useEffect, useRef } from "react";

// Procedural Milky Way-style backdrop for the hero: a tilted band of warm,
// dense stars with soft glow and a darker dust lane, over a sparse field of
// cool background stars. Seeded, so it draws the same sky on every visit.
// Decorative only - it is not a map of real stars (the real sky map with
// candidate positions comes later, from TIC coordinates).

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

export default function Starfield({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function draw() {
      if (!canvas || !ctx) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (w === 0 || h === 0) return;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const r = rng(20260925);

      // band runs from lower-left to upper-right
      const x0 = w * 0.25;
      const y0 = h * 1.05;
      const x1 = w * 1.05;
      const y1 = -h * 0.1;
      const dx = x1 - x0;
      const dy = y1 - y0;
      const len = Math.hypot(dx, dy);
      const nx = -dy / len;
      const ny = dx / len;
      const width = Math.min(w, h) * 0.26;

      // soft glow clouds along the band
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < 90; i++) {
        const t = r();
        const off = gauss(r) * width * 0.55;
        const cx = x0 + dx * t + nx * off;
        const cy = y0 + dy * t + ny * off;
        const rad = width * (0.35 + r() * 0.9);
        const core = Math.exp(-Math.pow((t - 0.55) / 0.35, 2));
        const warm = r() < 0.6;
        const col = warm ? "255,190,130" : "150,170,255";
        const a = 0.04 + 0.11 * core;
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
        g.addColorStop(0, `rgba(${col},${a})`);
        g.addColorStop(1, `rgba(${col},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, rad, 0, Math.PI * 2);
        ctx.fill();
      }

      // bright galactic core
      {
        const cx = x0 + dx * 0.55;
        const cy = y0 + dy * 0.55;
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, width * 1.6);
        g.addColorStop(0, "rgba(255,200,140,0.32)");
        g.addColorStop(0.35, "rgba(255,170,110,0.12)");
        g.addColorStop(1, "rgba(255,170,110,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, width * 1.6, 0, Math.PI * 2);
        ctx.fill();
      }

      // dense band stars
      for (let i = 0; i < 4200; i++) {
        const t = r();
        const off = gauss(r) * width * 0.45;
        const x = x0 + dx * t + nx * off;
        const y = y0 + dy * t + ny * off;
        const s = r() < 0.97 ? 0.35 + r() * 0.6 : 0.9 + r() * 0.9;
        const warm = r() < 0.55;
        const a = 0.35 + r() * 0.65;
        ctx.fillStyle = warm ? `rgba(255,214,170,${a})` : `rgba(210,225,255,${a})`;
        ctx.beginPath();
        ctx.arc(x, y, s, 0, Math.PI * 2);
        ctx.fill();
      }

      // dark dust lane slightly off the band centre
      ctx.globalCompositeOperation = "source-over";
      for (let i = 0; i < 160; i++) {
        const t = 0.15 + r() * 0.8;
        const off = width * 0.1 + gauss(r) * width * 0.06;
        const cx = x0 + dx * t + nx * off;
        const cy = y0 + dy * t + ny * off;
        const rad = width * (0.06 + r() * 0.14);
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
        g.addColorStop(0, "rgba(5,7,12,0.22)");
        g.addColorStop(1, "rgba(5,7,12,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, rad, 0, Math.PI * 2);
        ctx.fill();
      }

      // sparse background field
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < 500; i++) {
        const x = r() * w;
        const y = r() * h;
        const s = r() < 0.95 ? 0.3 + r() * 0.5 : 0.9 + r() * 0.8;
        ctx.fillStyle = `rgba(220,230,255,${0.2 + r() * 0.6})`;
        ctx.beginPath();
        ctx.arc(x, y, s, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";
    }

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, []);

  return <canvas ref={ref} aria-hidden="true" className={className} />;
}
