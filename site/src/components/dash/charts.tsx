"use client";

import { useEffect, useRef, useState } from "react";
import type { XY } from "@/lib/types";
import { percentile } from "@/lib/colormap";

// Plain-SVG charts sized to their container (measured, so text is never
// stretched). Every point drawn is a real data point from the export.

export function useWidth(fallback = 480) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(120, el.clientWidth)));
    ro.observe(el);
    setW(Math.max(120, el.clientWidth));
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export function niceTicks(lo: number, hi: number, n = 5): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  }
  return out;
}

function decimals(ticks: number[]): number {
  if (ticks.length < 2) return 2;
  const step = Math.abs(ticks[1] - ticks[0]);
  return Math.max(0, Math.min(5, Math.ceil(-Math.log10(step) + 0.001)));
}

export function robustDomain(values: number[], extra: number[] = [], pad = 0.08): [number, number] {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length === 0) return [0, 1];
  let lo = Math.min(percentile(v, 0.5), ...extra);
  let hi = Math.max(percentile(v, 99.5), ...extra);
  if (!(hi > lo)) {
    lo -= 0.001;
    hi += 0.001;
  }
  const p = (hi - lo) * pad;
  return [lo - p, hi + p];
}

export function PhaseScatter({
  raw,
  line,
  xDomain = [-0.5, 0.5],
  yDomain,
  height = 200,
  color = "#7dd3fc",
  lineColor = "#f8fafc",
  xLabel,
  yLabel,
  resid,
  residHeight = 56,
  xTickCount = 5,
  compact = false,
}: {
  raw: XY[];
  line?: XY[];
  xDomain?: [number, number];
  yDomain?: [number, number];
  height?: number;
  color?: string;
  lineColor?: string;
  xLabel?: string;
  yLabel?: string;
  resid?: XY[];
  residHeight?: number;
  xTickCount?: number;
  compact?: boolean;
}) {
  const [ref, width] = useWidth();
  const fs = compact ? 9 : 10;
  const padL = compact ? 34 : 44;
  const padR = 8;
  const padT = 6;
  const gap = resid ? 8 : 0;
  const rh = resid ? residHeight : 0;
  const padB = xLabel ? 30 : 18;
  const plotH = height - padT - padB - gap - rh;
  const inRange = raw.filter((p) => p[0] >= xDomain[0] && p[0] <= xDomain[1]);
  const lineIn = (line ?? []).filter((p) => p[0] >= xDomain[0] && p[0] <= xDomain[1]);
  const yd =
    yDomain ??
    robustDomain(
      inRange.map((p) => p[1]),
      lineIn.map((p) => p[1])
    );
  const sx = (x: number) => padL + ((x - xDomain[0]) / (xDomain[1] - xDomain[0])) * (width - padL - padR);
  const sy = (y: number) => padT + (1 - (y - yd[0]) / (yd[1] - yd[0])) * plotH;
  const yt = niceTicks(yd[0], yd[1], compact ? 3 : 4);
  const xt = niceTicks(xDomain[0], xDomain[1], xTickCount);
  const yDec = decimals(yt);
  const xDec = decimals(xt);

  let path = "";
  lineIn.forEach((p, i) => {
    path += `${i === 0 ? "M" : "L"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)} `;
  });

  // residual strip
  const rTop = padT + plotH + gap;
  const rv = (resid ?? []).filter((p) => p[0] >= xDomain[0] && p[0] <= xDomain[1]).map((p) => p[1]);
  const rMax = rv.length ? Math.max(1e-6, percentile(rv.map(Math.abs), 99)) * 1.2 : 1;
  const ry = (y: number) => rTop + (1 - (Math.max(-rMax, Math.min(rMax, y)) + rMax) / (2 * rMax)) * rh;
  const clampY = (y: number) => Math.max(padT, Math.min(padT + plotH, sy(y)));

  return (
    <div ref={ref} className="w-full">
      <svg width={width} height={height} className="block">
        {yt.map((t) => (
          <g key={`y${t}`}>
            <line x1={padL} x2={width - padR} y1={sy(t)} y2={sy(t)} className="stroke-line" strokeWidth={1} />
            <text x={padL - 5} y={sy(t) + 3} textAnchor="end" className="fill-faint font-mono" fontSize={fs}>
              {t.toFixed(yDec)}
            </text>
          </g>
        ))}
        {inRange.map((p, i) => (
          <circle key={i} cx={sx(p[0])} cy={clampY(p[1])} r={compact ? 0.9 : 1.1} fill={color} opacity={0.55} />
        ))}
        {path && <path d={path} fill="none" stroke={lineColor} strokeWidth={1.4} opacity={0.9} />}
        {resid && (
          <g>
            <line x1={padL} x2={width - padR} y1={ry(0)} y2={ry(0)} className="stroke-muted" strokeWidth={0.8} strokeDasharray="3 3" />
            {(resid ?? [])
              .filter((p) => p[0] >= xDomain[0] && p[0] <= xDomain[1])
              .map((p, i) => (
                <circle key={i} cx={sx(p[0])} cy={ry(p[1])} r={0.9} fill="#a78bfa" opacity={0.6} />
              ))}
            <text x={padL - 5} y={ry(0) + 3} textAnchor="end" className="fill-faint font-mono" fontSize={fs}>
              0
            </text>
          </g>
        )}
        {xt.map((t) => (
          <text
            key={`x${t}`}
            x={sx(t)}
            y={height - (xLabel ? 17 : 5)}
            textAnchor="middle"
            className="fill-faint font-mono"
            fontSize={fs}
          >
            {t.toFixed(xDec)}
          </text>
        ))}
        {xLabel && (
          <text x={(padL + width - padR) / 2} y={height - 3} textAnchor="middle" className="fill-muted" fontSize={fs}>
            {xLabel}
          </text>
        )}
        {yLabel && (
          <text
            transform={`translate(10 ${padT + plotH / 2}) rotate(-90)`}
            textAnchor="middle"
            className="fill-muted"
            fontSize={fs}
          >
            {yLabel}
          </text>
        )}
      </svg>
    </div>
  );
}

export function OCChart({
  points,
  height = 180,
}: {
  points: { epoch: number; oc_min: number; err_min: number }[];
  height?: number;
}) {
  const [ref, width] = useWidth();
  const padL = 44;
  const padR = 10;
  const padT = 8;
  const padB = 30;
  const xs = points.map((p) => p.epoch);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const xp = Math.max(1, (x1 - x0) * 0.06);
  const xd: [number, number] = [x0 - xp, x1 + xp];
  const ext = points.flatMap((p) => [p.oc_min - p.err_min, p.oc_min + p.err_min]);
  const m = Math.max(...ext.map(Math.abs), 0.01) * 1.15;
  const yd: [number, number] = [-m, m];
  const sx = (x: number) => padL + ((x - xd[0]) / (xd[1] - xd[0])) * (width - padL - padR);
  const sy = (y: number) => padT + (1 - (y - yd[0]) / (yd[1] - yd[0])) * (height - padT - padB);
  const yt = niceTicks(yd[0], yd[1], 4);
  const xt = niceTicks(xd[0], xd[1], 5).filter((t) => Math.abs(t - Math.round(t)) < 1e-9);
  const yDec = decimals(yt);
  return (
    <div ref={ref} className="w-full">
      <svg width={width} height={height} className="block">
        {yt.map((t) => (
          <g key={t}>
            <line x1={padL} x2={width - padR} y1={sy(t)} y2={sy(t)} className="stroke-line" />
            <text x={padL - 5} y={sy(t) + 3} textAnchor="end" className="fill-faint font-mono" fontSize={10}>
              {t.toFixed(yDec)}
            </text>
          </g>
        ))}
        <line x1={padL} x2={width - padR} y1={sy(0)} y2={sy(0)} className="stroke-muted" strokeDasharray="4 3" />
        {points.map((p) => (
          <g key={p.epoch}>
            <line
              x1={sx(p.epoch)}
              x2={sx(p.epoch)}
              y1={sy(p.oc_min - p.err_min)}
              y2={sy(p.oc_min + p.err_min)}
              stroke="#7dd3fc"
              strokeWidth={1.2}
            />
            <circle cx={sx(p.epoch)} cy={sy(p.oc_min)} r={3} fill="#7dd3fc" />
          </g>
        ))}
        {xt.map((t) => (
          <text key={t} x={sx(t)} y={height - 17} textAnchor="middle" className="fill-faint font-mono" fontSize={10}>
            {t}
          </text>
        ))}
        <text x={(padL + width - padR) / 2} y={height - 3} textAnchor="middle" className="fill-muted" fontSize={10}>
          Eclipse number (cycle)
        </text>
        <text transform={`translate(10 ${(padT + height - padB) / 2}) rotate(-90)`} textAnchor="middle" className="fill-muted" fontSize={10}>
          O - C (min)
        </text>
      </svg>
    </div>
  );
}
