// Stellar colour scale shared by the plate and the share card.

export const COLOR_SCALE: [number, number, number, number][] = [
  [2500, 255, 90, 50],
  [3500, 255, 128, 64],
  [4500, 255, 170, 90],
  [5300, 255, 205, 120],
  [5800, 255, 224, 150],
  [6300, 255, 238, 190],
  [7000, 245, 244, 240],
  [8000, 214, 226, 255],
  [10000, 175, 200, 255],
  [15000, 145, 178, 255],
  [30000, 120, 160, 255],
];

export function tempRgb(kelvin: number): [number, number, number] {
  const t = Math.min(30000, Math.max(2500, kelvin));
  let i = 0;
  while (i < COLOR_SCALE.length - 2 && t > COLOR_SCALE[i + 1][0]) i++;
  const a = COLOR_SCALE[i];
  const b = COLOR_SCALE[i + 1];
  const f = (t - a[0]) / (b[0] - a[0]);
  const mix = (x: number, y: number) => Math.round(x + (y - x) * f);
  return [mix(a[1], b[1]), mix(a[2], b[2]), mix(a[3], b[3])];
}

export function tempColor(kelvin: number): string {
  const [r, g, b] = tempRgb(kelvin);
  return `rgb(${r},${g},${b})`;
}

