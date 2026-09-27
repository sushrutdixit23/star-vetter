"use client";

import { useMemo, useState } from "react";
import type { Detail, Timeseries } from "@/lib/types";
import { percentile } from "@/lib/colormap";
import { PhaseScatter } from "../dash/charts";

function foldAt(bjd: number[], flux: number[], period: number, t0: number): [number, number][] {
  const out: [number, number][] = new Array(bjd.length);
  for (let i = 0; i < bjd.length; i++) {
    let phase = ((bjd[i] - t0) / period) % 1;
    if (phase < -0.5) phase += 1;
    if (phase >= 0.5) phase -= 1;
    out[i] = [phase, flux[i]];
  }
  return out;
}

// Interactive when a raw (un-folded) time series is available; otherwise
// falls back to the already-folded true-period view with the slider
// visibly disabled, rather than faking interactivity or hiding the section.
export default function FoldItYourself({
  d,
  ts,
  color,
}: {
  d: Detail | null;
  ts: Timeseries | null;
  color: string;
}) {
  const truePeriod = d?.period_true_days ?? null;
  const t0 = d?.t0_btjd ?? null;
  const [period, setPeriod] = useState(truePeriod ?? 1);
  const interactive = ts !== null && t0 !== null;

  const points = useMemo(() => {
    if (ts && t0 !== null) return foldAt(ts.bjd, ts.flux, period, t0);
    if (d) return d.fold.raw;
    return [];
  }, [ts, t0, period, d]);

  if (!d || truePeriod === null) {
    return <p className="text-xs text-faint">No signal data available for this candidate yet.</p>;
  }

  const flux = points.map((p) => p[1]);
  const lo = percentile(flux, 0.5);
  const hi = percentile(flux, 99.5);
  const pad = (hi - lo) * 0.08 || 0.01;

  return (
    <div>
      <PhaseScatter
        raw={points}
        height={220}
        color={color}
        xDomain={[-0.5, 0.5]}
        yDomain={[lo - pad, hi + pad]}
        xLabel="phase"
        yLabel="relative flux"
      />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-muted" htmlFor="fold-period">
          Period (days)
        </label>
        <input
          id="fold-period"
          type="range"
          min={truePeriod * 0.5}
          max={truePeriod * 2}
          step={truePeriod / 2000}
          value={period}
          disabled={!interactive}
          onChange={(e) => setPeriod(Number(e.target.value))}
          className="flex-1 accent-accent disabled:opacity-40"
        />
        <span className="w-20 text-right font-mono text-xs text-fg">{period.toFixed(5)}</span>
        <button
          type="button"
          onClick={() => setPeriod(truePeriod)}
          className="rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:text-fg"
        >
          Reset to best fit
        </button>
      </div>
      {!interactive && (
        <p className="mt-2 text-[11px] text-faint">
          Shown at the true period. The raw light curve needed to re-fold at other periods has not
          been exported yet - this slider unlocks automatically once it is.
        </p>
      )}
    </div>
  );
}
