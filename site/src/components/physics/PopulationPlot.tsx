"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { RvPoint } from "@/lib/physicsTypes";

const MONO = "var(--font-geist-mono)";
const W = 760, H = 430, L = 58, R = 18, T = 14, B = 48;

const LABEL: Record<string, string> = {
  moves: "bright star moves",
  consistent: "no clear motion",
  static_or_twin: "static, near-equal eclipses",
  substellar_or_blend: "static, shallow eclipse",
  blend_indicated: "static, deep eclipse",
};

function Mark({ v, x, y, hot }: { v: string; x: number; y: number; hot: boolean }) {
  const r = hot ? 7 : 5;
  if (v === "moves") return <circle cx={x} cy={y} r={r} className="fill-accent" opacity={hot ? 1 : 0.7} />;
  if (v === "blend_indicated") return <rect x={x - 6} y={y - 6} width="12" height="12" transform={`rotate(45 ${x} ${y})`} className="fill-accent-kill" />;
  if (v === "substellar_or_blend") return <path d={`M${x} ${y - r - 1}L${x + r + 1} ${y + r - 1}L${x - r - 1} ${y + r - 1}Z`} fill="none" className="stroke-muted" strokeWidth={hot ? 2.2 : 1.5} />;
  if (v === "static_or_twin") return <rect x={x - r + 1} y={y - r + 1} width={2 * r - 2} height={2 * r - 2} transform={`rotate(45 ${x} ${y})`} fill="none" className="stroke-muted" strokeWidth={hot ? 2.2 : 1.5} />;
  return <circle cx={x} cy={y} r={r - 0.5} fill="none" className="stroke-muted" strokeWidth={hot ? 2.2 : 1.5} />;
}

export default function PopulationPlot({ points }: { points: RvPoint[] }) {
  const router = useRouter();
  const wrap = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<RvPoint | null>(null);
  const xs = points.map((p) => p.depth_pct);
  const ys = points.map((p) => Math.max(p.rv_range_kms, 0.05));
  const x0 = Math.min(...xs) * 0.7;
  const x1 = Math.max(...xs) * 1.4;
  const y0 = Math.min(...ys) * 0.7;
  const y1 = Math.max(...ys) * 1.4;
  const rd = (v: number) => Math.round(v * 100) / 100;
  const sx = (v: number) => rd(L + ((Math.log10(v) - Math.log10(x0)) / (Math.log10(x1) - Math.log10(x0))) * (W - L - R));
  const sy = (v: number) => rd(T + (1 - (Math.log10(Math.max(v, 0.05)) - Math.log10(y0)) / (Math.log10(y1) - Math.log10(y0))) * (H - T - B));
  const decades = (a: number, b: number) => {
    const out: number[] = [];
    for (let v = Math.pow(10, Math.ceil(Math.log10(a))); v <= b * 1.0001; v *= 10) out.push(v);
    return out;
  };
  const counts: Record<string, number> = {};
  points.forEach((p) => { counts[p.verdict] = (counts[p.verdict] ?? 0) + 1; });
  const order = ["moves", "consistent", "static_or_twin", "substellar_or_blend", "blend_indicated"].filter((k) => counts[k]);
  const still = points.filter((p) => p.verdict !== "moves").sort((a, b) => a.tic - b.tic);

  return (
    <div>
      <div ref={wrap} className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`${points.length} survivors: eclipse depth against the range of Gaia's radial velocities for the bright star, coloured by whether the star visibly moves. A table follows the chart.`}>
          {decades(y0, y1).map((t) => (
            <g key={`y${t}`}>
              <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="stroke-line" />
              <text x={L - 8} y={sy(t) + 4} textAnchor="end" className="fill-faint" fontSize="11" fontFamily={MONO}>{t}</text>
            </g>
          ))}
          {decades(x0, x1).map((t) => (
            <g key={`x${t}`}>
              <line x1={sx(t)} x2={sx(t)} y1={T} y2={H - B} className="stroke-line" />
              <text x={sx(t)} y={H - B + 17} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>{t}</text>
            </g>
          ))}
          <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="fill-faint" fontSize="11" fontFamily={MONO}>eclipse depth (%)</text>
          <text x={14} y={(T + H - B) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`} className="fill-faint" fontSize="11" fontFamily={MONO}>Gaia velocity range (km/s)</text>
          {points.map((p) => (
            <g key={p.tic} onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)} onClick={() => router.push(`/candidates/${p.tic}`)} style={{ cursor: "pointer" }}>
              <circle cx={sx(p.depth_pct)} cy={sy(p.rv_range_kms)} r="13" fill="transparent" />
              <Mark v={p.verdict} x={sx(p.depth_pct)} y={sy(p.rv_range_kms)} hot={hover?.tic === p.tic} />
            </g>
          ))}
          {points.filter((p) => p.verdict === "blend_indicated").map((p) => (
            <text key={`l${p.tic}`} x={sx(p.depth_pct) + 11} y={sy(p.rv_range_kms) - 8} className="fill-fg" fontSize="11.5" fontFamily={MONO}>TIC {p.tic}</text>
          ))}
        </svg>
        {hover ? (
          <div className="pointer-events-none absolute z-10 rounded-md border border-line bg-panel-2 px-3 py-2 font-mono text-[11px] leading-relaxed text-fg shadow-lg" style={{ left: `${(sx(hover.depth_pct) / W) * 100}%`, top: `${(sy(hover.rv_range_kms) / H) * 100}%`, transform: "translate(-50%, calc(-100% - 14px))" }}>
            TIC {hover.tic} &middot; P {hover.period_days.toFixed(3)} d<br />
            depth {hover.depth_pct.toFixed(2)}% &middot; range {hover.rv_range_kms.toFixed(1)} km/s over {hover.n_transits} transits<br />
            <span className="text-muted">{LABEL[hover.verdict] ?? hover.verdict}</span>
          </div>
        ) : null}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted">
        {order.map((k) => (
          <li key={k} className="flex items-center gap-2">
            <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden="true"><Mark v={k} x={8} y={8} hot={false} /></svg>
            {LABEL[k]} <span className="font-mono text-faint">{counts[k]}</span>
          </li>
        ))}
      </ul>
      <details className="mt-4 rounded-xl border border-line">
        <summary className="cursor-pointer px-4 py-3 font-mono text-[11px] text-muted hover:text-fg">Table view: the {still.length} stars that do not clearly move</summary>
        <div className="overflow-x-auto border-t border-line">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="nav-caps font-mono text-[11px] text-muted">
              <tr><th className="p-3">Star</th><th className="p-3">Period (d)</th><th className="p-3">Depth</th><th className="p-3">Range (km/s)</th><th className="p-3">Transits</th><th className="p-3">Reading</th></tr>
            </thead>
            <tbody>
              {still.map((p) => (
                <tr key={p.tic} className="border-t border-line">
                  <td className="p-3"><a className="text-fg underline" href={`/candidates/${p.tic}`}>TIC {p.tic}</a></td>
                  <td className="p-3 font-mono">{p.period_days.toFixed(3)}</td>
                  <td className="p-3 font-mono">{p.depth_pct.toFixed(2)}%</td>
                  <td className="p-3 font-mono">{p.rv_range_kms.toFixed(1)}</td>
                  <td className="p-3 font-mono">{p.n_transits}</td>
                  <td className="p-3 text-muted">{LABEL[p.verdict] ?? p.verdict}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
