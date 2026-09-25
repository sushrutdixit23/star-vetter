// Sky geometry for the all-sky map: Mollweide projection (equal-area) of
// equatorial coordinates, plus the galactic plane traced by rotating
// galactic (l, b = 0) into J2000 RA/Dec. Pure math - nothing decorative.

const DEG = Math.PI / 180;

// J2000 equatorial -> galactic rotation matrix (Hipparcos convention).
// Its transpose takes galactic back to equatorial.
const T = [
  [-0.0548755604, -0.873437090, -0.4838350155],
  [0.4941094279, -0.44482963, 0.7469822445],
  [-0.867666149, -0.1980763734, 0.4559837762],
];

export function galacticToEquatorial(lDeg: number, bDeg: number): [number, number] {
  const l = lDeg * DEG;
  const b = bDeg * DEG;
  const g = [Math.cos(b) * Math.cos(l), Math.cos(b) * Math.sin(l), Math.sin(b)];
  const e = [0, 1, 2].map((i) => T[0][i] * g[0] + T[1][i] * g[1] + T[2][i] * g[2]);
  let ra = Math.atan2(e[1], e[0]) / DEG;
  if (ra < 0) ra += 360;
  const dec = Math.asin(Math.max(-1, Math.min(1, e[2]))) / DEG;
  return [ra, dec];
}

// Mollweide: returns x in [-2*sqrt2, 2*sqrt2], y in [-sqrt2, sqrt2].
// RA = 0h sits in the centre and increases to the LEFT (sky convention).
export function mollweide(raDeg: number, decDeg: number): [number, number] {
  let lam = -((((raDeg + 180) % 360) + 360) % 360 - 180) * DEG;
  if (lam > Math.PI) lam -= 2 * Math.PI;
  const phi = decDeg * DEG;
  let th = phi;
  if (Math.abs(Math.abs(phi) - Math.PI / 2) < 1e-9) {
    th = phi;
  } else {
    for (let i = 0; i < 30; i++) {
      const f = 2 * th + Math.sin(2 * th) - Math.PI * Math.sin(phi);
      const d = 2 + 2 * Math.cos(2 * th);
      if (Math.abs(d) < 1e-12) break;
      const step = f / d;
      th -= step;
      if (Math.abs(step) < 1e-10) break;
    }
  }
  return [((2 * Math.SQRT2) / Math.PI) * lam * Math.cos(th), Math.SQRT2 * Math.sin(th)];
}

// A projected polyline broken wherever it wraps across the map edge.
export function projectedPath(
  pts: [number, number][],
  sx: (x: number) => number,
  sy: (y: number) => number
): string {
  let d = "";
  let prevX: number | null = null;
  for (const [ra, dec] of pts) {
    const [x, y] = mollweide(ra, dec);
    const jump = prevX !== null && Math.abs(x - prevX) > 1.5;
    d += `${prevX === null || jump ? "M" : "L"}${sx(x).toFixed(1)},${sy(y).toFixed(1)} `;
    prevX = x;
  }
  return d;
}

export function galacticLine(bDeg: number, step = 2): [number, number][] {
  const out: [number, number][] = [];
  for (let l = 0; l <= 360; l += step) out.push(galacticToEquatorial(l, bDeg));
  return out;
}

export function fmtRA(raDeg: number): string {
  const h = raDeg / 15;
  const hh = Math.floor(h);
  const mm = Math.floor((h - hh) * 60);
  const ss = ((h - hh) * 60 - mm) * 60;
  return `${String(hh).padStart(2, "0")}h ${String(mm).padStart(2, "0")}m ${ss.toFixed(1)}s`;
}

export function fmtDec(decDeg: number): string {
  const s = decDeg < 0 ? "-" : "+";
  const a = Math.abs(decDeg);
  const dd = Math.floor(a);
  const mm = Math.floor((a - dd) * 60);
  const ss = ((a - dd) * 60 - mm) * 60;
  return `${s}${String(dd).padStart(2, "0")}d ${String(mm).padStart(2, "0")}m ${ss.toFixed(0)}s`;
}
