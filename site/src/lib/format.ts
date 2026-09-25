export function fmtNum(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  return x.toFixed(digits);
}

export function fmtDepth(frac: number): string {
  return `${(frac * 100).toFixed(3)}%`;
}

export function fmtPpm(ppm: number | null): string {
  if (ppm === null) return "n/a";
  return `${Math.round(ppm).toLocaleString("en-US")} ppm`;
}

export function fmtArcsec(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  return `${Math.round(x)}"`;
}
