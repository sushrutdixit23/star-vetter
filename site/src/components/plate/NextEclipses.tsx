"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { PredictionStar } from "@/lib/types";

// Eclipse times shown on a candidate's plate come only from the f13 ephemeris
// (export_predictions.py), which carries an honest uncertainty and has been
// tested on sectors it was not fitted to. The pipeline's own search ephemeris
// is deliberately NOT used here: it is accurate near the data it was measured
// on, but a small period error multiplied by a thousand cycles moves an
// eclipse by hours, so printing its clock time to the minute would be false
// precision.

function utcMs(s: string): number {
  return new Date(s.replace(" ", "T") + "Z").getTime();
}

function fmtSigma(min: number): string {
  return min < 90 ? `${min.toFixed(0)} min` : `${(min / 60).toFixed(1)} h`;
}

export default function NextEclipses({ pred }: { pred: PredictionStar | null }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);

  if (!pred) {
    return (
      <div className="rounded-lg border border-line bg-panel-2 p-3">
        <div className="nav-caps text-[11px] text-muted">Next eclipses</div>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          No eclipse clock is published for this star. The search ephemeris is only accurate near the data it was measured on, so a
          time a year from now would be a guess.
        </p>
        <Link href="/predictions" className="nav-caps mt-2 inline-block font-mono text-[10px] text-accent hover:text-fg">How predictions are chosen &rarr;</Link>
      </div>
    );
  }

  const upcoming = pred.predictions.filter((p) => now === null || utcMs(p.utc) > now).slice(0, 3);
  const shown = upcoming.length > 0 ? upcoming : pred.predictions.slice(-1);

  return (
    <div className="rounded-lg border border-line bg-panel-2 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="nav-caps text-[11px] text-muted">Next primary eclipses (UTC)</div>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] ${pred.grade === "VALIDATED" ? "border-emerald-400/40 text-emerald-300" : "border-line text-muted"}`}>
          {pred.grade === "VALIDATED" ? "Validated" : "Not validated"}
        </span>
      </div>
      <ul className="mt-2 space-y-1 text-xs">
        {shown.map((p) => (
          <li key={p.cycle} className="flex flex-wrap justify-between gap-x-3 font-mono text-fg">
            <span className="text-muted">Sector {p.sector}{p.approximate ? "*" : ""}</span>
            <span className="whitespace-nowrap">{p.utc.slice(0, 16)} <span className="text-muted">&plusmn; {fmtSigma(p.sigma_min)}</span></span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] leading-relaxed text-faint">
        From a fitted ephemeris with its uncertainty, geocentric UTC. To be graded against TESS Year 9 data.{" "}
        <Link href="/predictions" className="text-accent hover:text-fg">All predictions &rarr;</Link>
      </p>
    </div>
  );
}
