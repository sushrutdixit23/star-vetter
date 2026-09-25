"use client";

import { useState, useRef } from "react";

type RawPoint = [number, number];
type BinPoint = [number, number | null];

// The full phase-folded light curve: raw per-cadence flux as faint scatter,
// the binned curve as a solid line on top, with a hover readout. Still no
// charting library - just SVG and mouse math, same approach as MiniChart.
export default function LightCurveChart({
  raw,
  binned,
  color = "#38bdf8",
  labelSize = 11,
}: {
  raw: RawPoint[];
  binned: BinPoint[];
  color?: string;
  labelSize?: number;
}) {
  const width = 800;
  const height = 320;
  const padL = 16 + labelSize * 3.6;
  const padR = 8 + labelSize * 1.6;
  const padT = 16;
  const padB = 16 + labelSize * 1.9;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const rawFlux = raw.map((p) => p[1]);
  const binnedFlux = binned
    .map((p) => p[1])
    .filter((v): v is number => v !== null);
  const allFlux = [...rawFlux, ...binnedFlux];
  const min = Math.min(...allFlux);
  const max = Math.max(...allFlux);
  const span = max - min || 1;
  const pad = span * 0.08;

  const x = (phase: number) => padL + ((phase + 0.5) / 1) * plotW;
  const y = (flux: number) =>
    padT + plotH - ((flux - (min - pad)) / (span + 2 * pad)) * plotH;

  let linePath = "";
  let drawing = false;
  for (const [phase, flux] of binned) {
    if (flux === null) {
      drawing = false;
      continue;
    }
    linePath += `${drawing ? "L" : "M"}${x(phase).toFixed(2)},${y(
      flux
    ).toFixed(2)} `;
    drawing = true;
  }

  const xTicks = [-0.5, -0.25, 0, 0.25, 0.5];
  const yMid = (min + max) / 2;
  const yTicks = [min, yMid, max];

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const phase = (px - padL) / plotW - 0.5;
    let nearest = 0;
    let nearestDist = Infinity;
    binned.forEach((p, i) => {
      if (p[1] === null) return;
      const d = Math.abs(p[0] - phase);
      if (d < nearestDist) {
        nearestDist = d;
        nearest = i;
      }
    });
    setHoverIdx(nearest);
  }

  const hover = hoverIdx !== null ? binned[hoverIdx] : null;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={padL}
              x2={width - padR}
              y1={y(t)}
              y2={y(t)}
              className="stroke-line"
              strokeWidth={1}
            />
            <text
              x={padL - 8}
              y={y(t)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-faint"
              fontSize={labelSize}
              fontFamily="var(--font-geist-mono, monospace)"
            >
              {t.toFixed(3)}
            </text>
          </g>
        ))}

        {xTicks.map((t, i) => (
          <g key={i}>
            <text
              x={x(t)}
              y={height - padB + labelSize * 1.5}
              textAnchor="middle"
              className="fill-faint"
              fontSize={labelSize}
              fontFamily="var(--font-geist-mono, monospace)"
            >
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <text
          x={width / 2}
          y={height - 2}
          textAnchor="middle"
          className="fill-faint"
          fontSize={labelSize * 0.9}
        >
          Phase
        </text>

        {raw.map((p, i) => (
          <circle
            key={i}
            cx={x(p[0])}
            cy={y(p[1])}
            r={1.4}
            fill={color}
            opacity={0.18}
          />
        ))}

        <path d={linePath} fill="none" stroke={color} strokeWidth={2} />

        {hover && hover[1] !== null && (
          <>
            <line
              x1={x(hover[0])}
              x2={x(hover[0])}
              y1={padT}
              y2={height - padB}
              className="stroke-muted"
              strokeWidth={1}
            />
            <circle
              cx={x(hover[0])}
              cy={y(hover[1])}
              r={4}
              fill="white"
              stroke={color}
              strokeWidth={2}
            />
          </>
        )}
      </svg>

      {hover && hover[1] !== null && (
        <div className="pointer-events-none absolute top-2 right-2 rounded-md border border-line bg-panel/90 px-2.5 py-1.5 font-mono text-xs text-fg backdrop-blur">
          phase {hover[0].toFixed(3)} &middot; flux {hover[1].toFixed(4)}
        </div>
      )}
    </div>
  );
}
