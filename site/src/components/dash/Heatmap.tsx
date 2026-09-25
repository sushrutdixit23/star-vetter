import type { Neighbour, XY } from "@/lib/types";
import { inferno } from "@/lib/colormap";

// One TESS pixel cutout drawn cell by cell (1 cell = 1 TESS pixel = 21").
// Array rows are y (row 0 at the bottom, matching origin="lower" in
// diag_pixel.py's own figure), columns are x.
export default function Heatmap({
  grid,
  lo,
  hi,
  stretch = "linear",
  target,
  centroid,
  neighbours,
  label,
}: {
  grid: (number | null)[][];
  lo: number;
  hi: number;
  stretch?: "linear" | "sqrt";
  target: XY;
  centroid?: XY;
  neighbours: Neighbour[];
  label: string;
}) {
  const ny = grid.length;
  const nx = grid[0]?.length ?? 0;
  const S = 20;
  const W = nx * S;
  const H = ny * S;
  const px = (x: number) => (x + 0.5) * S;
  const py = (y: number) => H - (y + 0.5) * S;
  const norm = (v: number) => {
    const t = (v - lo) / (hi - lo || 1);
    const c = Math.max(0, Math.min(1, t));
    return stretch === "sqrt" ? Math.sqrt(c) : c;
  };
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 text-center text-[11px] text-muted">{label}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block aspect-square w-full rounded border border-line">
        {grid.map((row, j) =>
          row.map((v, i) => (
            <rect
              key={`${i}-${j}`}
              x={i * S}
              y={H - (j + 1) * S}
              width={S + 0.5}
              height={S + 0.5}
              fill={v === null ? "#0b0f17" : inferno(norm(v))}
            />
          ))
        )}
        {neighbours.map((n) =>
          n.capable ? (
            <g key={n.tic} stroke="#84cc16" strokeWidth={2}>
              <line x1={px(n.x) - 4} y1={py(n.y) - 4} x2={px(n.x) + 4} y2={py(n.y) + 4} />
              <line x1={px(n.x) - 4} y1={py(n.y) + 4} x2={px(n.x) + 4} y2={py(n.y) - 4} />
            </g>
          ) : (
            <circle key={n.tic} cx={px(n.x)} cy={py(n.y)} r={2.2} fill="none" stroke="#67e8f9" strokeWidth={0.9} opacity={0.8} />
          )
        )}
        {centroid && (
          <circle cx={px(centroid[0])} cy={py(centroid[1])} r={8} fill="none" stroke="#facc15" strokeWidth={2} />
        )}
        <g stroke="#f43f5e" strokeWidth={2.4}>
          <line x1={px(target[0]) - 9} y1={py(target[1])} x2={px(target[0]) + 9} y2={py(target[1])} />
          <line x1={px(target[0])} y1={py(target[1]) - 9} x2={px(target[0])} y2={py(target[1]) + 9} />
        </g>
      </svg>
    </figure>
  );
}
