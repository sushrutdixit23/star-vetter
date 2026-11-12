import { memo } from "react";
import type { CurveSet } from "@/lib/physicsTypes";

// Chart primitives for the Physics page. Plain SVG, no chart library, same approach as MiniChart.
// Everything is drawn from the exported curve files; nothing is smoothed or re-fitted here.

const rd = (v: number) => Math.round(v * 100) / 100;

export const WIN_W = 480;
export const WIN_H = 330;
const PAD = { l: 52, r: 12, t: 14, b: 44 };
const FLUX_BOTTOM = 218; // y of the flux panel's bottom edge
const RES_TOP = 234;
const RES_BOTTOM = 290;

export function niceTicks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}

/** Shared flux range for the two eclipse windows of one star, so their depths compare by eye. */
export function fluxRange(c: CurveSet): [number, number] {
  const depth = 1 - c.min_flux;
  return [c.min_flux - 0.05 * depth - 0.0005, 1 + 0.05 * depth + 0.001];
}

export function windowHalfWidth(c: CurveSet): number {
  return 1.62 * c.duration_phase;
}

export function eclipseCentres(c: CurveSet): { primary: number; secondary: number } {
  return { primary: 0, secondary: c.secondary_phase_ellc ?? c.secondary_phase_kepler };
}

function xOfHours(h: number, halfHours: number): number {
  return rd(PAD.l + ((h + halfHours) / (2 * halfHours)) * (WIN_W - PAD.l - PAD.r));
}

export function cursorX(c: CurveSet, centre: number, half: number, phase: number): number | null {
  const d = phase - centre;
  if (Math.abs(d) > half) return null;
  const halfHours = half * c.period_days * 24;
  return xOfHours(d * c.period_days * 24, halfHours);
}

export function cursorY(flux: number, yMin: number, yMax: number): number {
  return rd(PAD.t + (1 - (flux - yMin) / (yMax - yMin)) * (FLUX_BOTTOM - PAD.t));
}

interface WindowProps {
  curve: CurveSet;
  centre: number;
  yMin: number;
  yMax: number;
  title: string;
  label: string;
  published?: { x: number[]; y: number[] } | null;
  modelName?: string;
}

/** One eclipse: binned data with 1-sigma bars, best-fit model, and the residuals underneath. */
export const EclipseWindow = memo(function EclipseWindow({ curve, centre, yMin, yMax, title, label, published, modelName }: WindowProps) {
  const half = windowHalfWidth(curve);
  const P = curve.period_days;
  const halfHours = half * P * 24;
  const sx = (ph: number) => xOfHours((ph - centre) * P * 24, halfHours);
  const sy = (f: number) => rd(PAD.t + (1 - (f - yMin) / (yMax - yMin)) * (FLUX_BOTTOM - PAD.t));

  const idx: number[] = [];
  curve.data.x.forEach((x, i) => {
    if (Math.abs(x - centre) <= half) idx.push(i);
  });
  const resPpt = idx.map((i) => curve.residual[i] * 1000);
  const resLim = Math.max(1, Math.ceil(Math.max(0.5, ...resPpt.map((r) => Math.abs(r))) * 1.1));
  const sr = (r: number) => rd((RES_TOP + RES_BOTTOM) / 2 - (r / resLim) * ((RES_BOTTOM - RES_TOP) / 2));

  const path = (m: { x: number[]; y: number[] }) => {
    let d = "";
    for (let i = 0; i < m.x.length; i++) {
      if (Math.abs(m.x[i] - centre) > half * 1.01) continue;
      d += (d ? "L" : "M") + sx(m.x[i]).toFixed(1) + " " + sy(Math.min(Math.max(m.y[i], yMin), yMax)).toFixed(1);
    }
    return d;
  };

  const yTicks = niceTicks(yMin, yMax, 4);
  const xTicks = niceTicks(-halfHours, halfHours, 4);
  const dec = yMax - yMin < 0.05 ? 3 : 2;

  return (
    <svg viewBox={`0 0 ${WIN_W} ${WIN_H}`} className="block h-auto w-full" role="img" aria-label={`${title}: ${label}. Binned TESS flux with one-sigma bars, the best-fit model, and residuals.`}>
      <text x={PAD.l} y={PAD.t - 2} className="fill-muted" fontSize="11" fontFamily="var(--font-geist-mono)">{title}</text>
      {yTicks.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={WIN_W - PAD.r} y1={sy(t)} y2={sy(t)} className="stroke-line" strokeWidth="1" />
          <text x={PAD.l - 6} y={sy(t) + 3.5} textAnchor="end" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">{t.toFixed(dec)}</text>
        </g>
      ))}
      <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={FLUX_BOTTOM} className="stroke-line" />
      {idx.map((i) => {
        const x = sx(curve.data.x[i]);
        const y = curve.data.y[i];
        const e = curve.data.e[i];
        return <line key={`e${i}`} x1={x} x2={x} y1={sy(y - e)} y2={sy(y + e)} className="stroke-muted" strokeWidth="1" opacity="0.55" />;
      })}
      {idx.map((i) => (
        <circle key={`d${i}`} cx={sx(curve.data.x[i])} cy={sy(curve.data.y[i])} r="2.3" className="fill-fg" opacity="0.88" />
      ))}
      {published ? <path d={path(published)} fill="none" className="stroke-accent-cool" strokeWidth="1.5" strokeDasharray="5 4" /> : null}
      <path d={path(curve.model)} fill="none" className="stroke-accent" strokeWidth="1.8" />
      <text x={WIN_W - PAD.r} y={PAD.t - 2} textAnchor="end" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">{modelName ?? "best-fit model"}</text>
      <line x1={PAD.l} x2={WIN_W - PAD.r} y1={sr(0)} y2={sr(0)} className="stroke-line" />
      {[-resLim, 0, resLim].map((t) => (
        <text key={t} x={PAD.l - 6} y={sr(t) + 3.5} textAnchor="end" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">{t}</text>
      ))}
      {resPpt.map((r, k) => (
        <circle key={`r${k}`} cx={sx(curve.data.x[idx[k]])} cy={sr(Math.max(-resLim, Math.min(resLim, r)))} r="2" className="fill-muted" opacity="0.8" />
      ))}
      <text x={12} y={(RES_TOP + RES_BOTTOM) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(RES_TOP + RES_BOTTOM) / 2})`} className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">residual (ppt)</text>
      <text x={12} y={(PAD.t + FLUX_BOTTOM) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(PAD.t + FLUX_BOTTOM) / 2})`} className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">relative flux</text>
      {xTicks.map((t) => (
        <g key={t}>
          <line x1={xOfHours(t, halfHours)} x2={xOfHours(t, halfHours)} y1={RES_BOTTOM} y2={RES_BOTTOM + 4} className="stroke-faint" />
          <text x={xOfHours(t, halfHours)} y={RES_BOTTOM + 17} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">{t}</text>
        </g>
      ))}
      <text x={(PAD.l + WIN_W - PAD.r) / 2} y={WIN_H - 8} textAnchor="middle" className="fill-faint" fontSize="10.5" fontFamily="var(--font-geist-mono)">hours from mid-eclipse</text>
    </svg>
  );
});

/** A moving marker laid over an EclipseWindow with the same viewBox. */
export function CursorOverlay({ curve, centre, yMin, yMax, phase, flux }: { curve: CurveSet; centre: number; yMin: number; yMax: number; phase: number; flux: number }) {
  const x = cursorX(curve, centre, windowHalfWidth(curve), phase);
  if (x === null) return null;
  const y = cursorY(Math.min(Math.max(flux, yMin), yMax), yMin, yMax);
  return (
    <svg viewBox={`0 0 ${WIN_W} ${WIN_H}`} className="pointer-events-none absolute inset-0 block h-full w-full" aria-hidden="true">
      <line x1={x} x2={x} y1={PAD.t} y2={RES_BOTTOM} className="stroke-accent-cool" strokeWidth="1" strokeDasharray="3 3" opacity="0.9" />
      <circle cx={x} cy={y} r="4.5" className="fill-accent-cool stroke-canvas" strokeWidth="1.5" />
    </svg>
  );
}
