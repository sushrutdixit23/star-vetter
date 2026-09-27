// Colour maps for the pixel images. RAMP runs from near-black through blue
// to white, matching the site's night palette (it replaces the old
// matplotlib "inferno" ramp, whose purple/orange did not fit the theme).
type RGB = [number, number, number];

const RAMP: RGB[] = [
  [7, 11, 24], [17, 22, 46], [28, 34, 64], [58, 67, 99], [90, 99, 144],
  [140, 154, 199], [180, 191, 222], [201, 207, 230], [255, 255, 255],
];

export function inferno(t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const f = x - i;
  const a = RAMP[i];
  const b = RAMP[i + 1];
  const c = [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const s = [...values].sort((a, b) => a - b);
  const idx = Math.min(s.length - 1, Math.max(0, (p / 100) * (s.length - 1)));
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return s[lo] + (s[hi] - s[lo]) * (idx - lo);
}
