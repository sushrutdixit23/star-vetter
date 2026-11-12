// Orbit and eclipse geometry for the Physics page. Mirrored line for line in export_physics.py, and
// tests/test_physics_page.py checks the two agree and that the geometry matches ellc's eclipse timing.
//
// Convention (the one ellc and the eclipsing-binary literature use): omega is the argument of periastron
// of the primary's orbit; mid-primary-eclipse is phase 0 and happens when true anomaly + omega = 90 deg.
// Positions are star 2 relative to star 1 in units of the semi-major axis; z > 0 means star 2 is nearer
// the observer, so star 1 is being eclipsed.

const TAU = 2 * Math.PI;

export function keplerE(M: number, e: number): number {
  const m = ((M % TAU) + TAU) % TAU;
  let E = e < 0.8 ? m + e * Math.sin(m) : Math.PI;
  for (let i = 0; i < 60; i++) {
    const d = (E - e * Math.sin(E) - m) / (1 - e * Math.cos(E));
    E -= d;
    if (Math.abs(d) < 1e-13) break;
  }
  return E;
}

export function trueAnomaly(M: number, e: number): number {
  const E = keplerE(M, e);
  return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2));
}

export function meanAnomaly(nu: number, e: number): number {
  const E = 2 * Math.atan2(Math.sqrt(1 - e) * Math.sin(nu / 2), Math.sqrt(1 + e) * Math.cos(nu / 2));
  return E - e * Math.sin(E);
}

export interface Pos {
  x: number; // sky, along the orbit's long axis as seen from Earth
  y: number; // sky, perpendicular (small for edge-on orbits)
  z: number; // toward the observer
  r: number; // separation in 3-D
  u: number; // true anomaly + omega
}

export function skyPosition(phase: number, e: number, omegaRad: number, inclDeg: number): Pos {
  const m = meanAnomaly(Math.PI / 2 - omegaRad, e) + TAU * phase;
  const nu = trueAnomaly(m, e);
  const r = (1 - e * e) / (1 + e * Math.cos(nu));
  const u = nu + omegaRad;
  const i = (inclDeg * Math.PI) / 180;
  return { x: r * Math.cos(u), y: r * Math.sin(u) * Math.cos(i), z: r * Math.sin(u) * Math.sin(i), r, u };
}

export function secondaryPhase(e: number, omegaRad: number): number {
  const m1 = meanAnomaly(Math.PI / 2 - omegaRad, e);
  const m2 = meanAnomaly((3 * Math.PI) / 2 - omegaRad, e);
  return (((m2 - m1) / TAU) % 1 + 1) % 1;
}

/** Orbit outline sampled uniformly in true anomaly: sky projection and the face-on orbital plane
 * (with the observer toward +y). */
export function outline(e: number, omegaRad: number, inclDeg: number, n = 240) {
  const sky: [number, number][] = [];
  const plane: [number, number][] = [];
  const i = (inclDeg * Math.PI) / 180;
  for (let k = 0; k <= n; k++) {
    const nu = (TAU * k) / n;
    const r = (1 - e * e) / (1 + e * Math.cos(nu));
    const u = nu + omegaRad;
    sky.push([r * Math.cos(u), r * Math.sin(u) * Math.cos(i)]);
    plane.push([r * Math.cos(u), r * Math.sin(u)]);
  }
  return { sky, plane };
}

export type EclipseState = "primary" | "secondary" | "none";

/** Which eclipse (if any) is under way: the discs overlap on the sky. */
export function eclipseState(p: Pos, r1: number, r2: number): EclipseState {
  if (Math.hypot(p.x, p.y) >= r1 + r2) return "none";
  return p.z > 0 ? "primary" : "secondary";
}

/** Linear interpolation of a tabulated curve; `x` must be ascending. Values outside return `fallback`. */
export function interp(xs: number[], ys: number[], x: number, fallback = 1): number {
  if (!xs.length || x < xs[0] || x > xs[xs.length - 1]) return fallback;
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= x) lo = mid;
    else hi = mid;
  }
  const t = (x - xs[lo]) / (xs[hi] - xs[lo] || 1);
  return ys[lo] + t * (ys[hi] - ys[lo]);
}

/** Wrap a phase into the [-0.25, 0.75) range the light curves are tabulated on. */
export function wrapPhase(p: number): number {
  return ((((p + 0.25) % 1) + 1) % 1) - 0.25;
}
