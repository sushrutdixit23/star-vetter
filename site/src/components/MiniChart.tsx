type Point = [number, number | null];

// A small inline SVG sparkline of the binned, phase-folded light curve - no
// charting library needed for a 60-point line. Used as the card thumbnail;
// the full interactive chart (with the raw scatter too) lives on the
// candidate detail page.
export default function MiniChart({
  binned,
  width = 240,
  height = 72,
  color = "#38bdf8",
}: {
  binned: Point[];
  width?: number;
  height?: number;
  color?: string;
}) {
  const values = binned
    .map((p) => p[1])
    .filter((v): v is number => v !== null);
  if (values.length === 0) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 4;

  const x = (phase: number) => ((phase + 0.5) * (width - 2 * pad)) + pad;
  const y = (flux: number) =>
    height - pad - ((flux - min) / span) * (height - 2 * pad);

  let d = "";
  let drawing = false;
  for (const [phase, flux] of binned) {
    if (flux === null) {
      drawing = false;
      continue;
    }
    const cmd = drawing ? "L" : "M";
    d += `${cmd}${x(phase).toFixed(1)},${y(flux).toFixed(1)} `;
    drawing = true;
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto"
      preserveAspectRatio="none"
    >
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}
