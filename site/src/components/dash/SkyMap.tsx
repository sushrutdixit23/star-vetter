import type { SkyPoint } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";
import { galacticLine, mollweide, projectedPath } from "@/lib/sky";

// All-sky Mollweide map (equatorial J2000, RA 0h at centre, increasing to
// the left) with every confirmed candidate at its real TIC position and the
// galactic plane (b = 0, plus b = +/-10 deg) computed from the J2000 ->
// galactic rotation.
export default function SkyMap({
  points,
  highlight,
  className = "",
}: {
  points: SkyPoint[];
  highlight?: number;
  className?: string;
}) {
  const W = 560;
  const H = 280;
  const R = 2 * Math.SQRT2;
  const sx = (x: number) => W / 2 + (x / R) * (W / 2 - 4);
  const sy = (y: number) => H / 2 - (y / Math.SQRT2) * (H / 2 - 4);

  const outline: [number, number][] = [];
  for (let d = -90; d <= 90; d += 3) outline.push([180.0001, d]);
  const outline2: [number, number][] = [];
  for (let d = 90; d >= -90; d -= 3) outline2.push([179.9999, d]);

  const decLines = [-60, -30, 0, 30, 60].map((dec) => {
    const pts: [number, number][] = [];
    for (let ra = 180.001; ra <= 540; ra += 4) pts.push([ra % 360, dec]);
    return { dec, d: projectedPath(pts, sx, sy) };
  });
  const raLines = [0, 60, 120, 240, 300].map((ra) => {
    const pts: [number, number][] = [];
    for (let dec = -90; dec <= 90; dec += 3) pts.push([ra, dec]);
    return { ra, d: projectedPath(pts, sx, sy) };
  });

  const shown = points.filter((p) => p.ra !== null && p.dec !== null);
  const hi = shown.find((p) => p.tic === highlight);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={className} role="img" aria-label="Sky positions of confirmed candidates">
      <path d={projectedPath(outline, sx, sy) + projectedPath(outline2, sx, sy)} fill="rgba(5,7,12,0.35)" stroke="rgba(255,255,255,0.35)" strokeWidth={1} />
      {decLines.map((l) => (
        <path key={`d${l.dec}`} d={l.d} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />
      ))}
      {raLines.map((l) => (
        <path key={`r${l.ra}`} d={l.d} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />
      ))}
      <path d={projectedPath(galacticLine(10), sx, sy)} fill="none" stroke="rgba(251,191,36,0.25)" strokeWidth={0.8} strokeDasharray="3 4" />
      <path d={projectedPath(galacticLine(-10), sx, sy)} fill="none" stroke="rgba(251,191,36,0.25)" strokeWidth={0.8} strokeDasharray="3 4" />
      <path d={projectedPath(galacticLine(0), sx, sy)} fill="none" stroke="rgba(251,191,36,0.6)" strokeWidth={1.2} />
      {[0, 6, 18].map((h) => {
        const [x, y] = mollweide(h * 15 + 0.001, 0);
        return (
          <text key={h} x={sx(x)} y={sy(y) - 4} textAnchor="middle" fontSize={11} fill="rgba(255,255,255,0.45)" className="font-mono">
            {h}h
          </text>
        );
      })}
      {shown.map((p) => {
        const [x, y] = mollweide(p.ra as number, p.dec as number);
        return (
          <circle key={p.tic} cx={sx(x)} cy={sy(y)} r={p.tic === highlight ? 0 : 3} fill={TIER_STYLE[p.tier].chart} stroke="rgba(5,7,12,0.8)" strokeWidth={0.8}>
            <title>{`TIC ${p.tic}`}</title>
          </circle>
        );
      })}
      {hi && (() => {
        const [x, y] = mollweide(hi.ra as number, hi.dec as number);
        return (
          <g>
            <circle cx={sx(x)} cy={sy(y)} r={9} fill="none" stroke="#fde68a" strokeWidth={1} opacity={0.6} />
            <circle cx={sx(x)} cy={sy(y)} r={4.5} fill="#fde68a" />
          </g>
        );
      })()}
      <text x={6} y={H - 6} fontSize={9} fill="rgba(255,255,255,0.4)">
        Equatorial J2000, Mollweide - gold line: galactic plane
      </text>
    </svg>
  );
}
