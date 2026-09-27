"use client";

import { useMemo } from "react";
import type { Detail } from "@/lib/types";

// BTJD (this pipeline's time convention throughout Detail) is BJD_TDB minus
// 2457000. This ignores the ~69s TDB/UTC offset and any light-travel
// correction to the viewer's location - fine for a display convenience,
// not for anything that needs sub-minute accuracy.
function btjdToDate(btjd: number): Date {
  const jd = btjd + 2457000;
  const unixMs = (jd - 2440587.5) * 86400000;
  return new Date(unixMs);
}

function fmt(dt: Date): string {
  return dt.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export default function NextEclipses({ d }: { d: Detail | null }) {
  const events = useMemo(() => {
    if (!d) return [];
    const period = d.period_true_days;
    const t0 = d.t0_btjd;
    const secPhase = d.secondary?.detected ? d.secondary.phase : d.fold.second_phase;

    const nowBtjd = Date.now() / 86400000 + 2440587.5 - 2457000;
    const startEpoch = Math.floor((nowBtjd - t0) / period);

    const out: { label: string; date: Date }[] = [];
    for (let e = startEpoch; out.length < 6 && e < startEpoch + 8; e++) {
      const primaryBtjd = t0 + e * period;
      if (primaryBtjd > nowBtjd) out.push({ label: "Primary", date: btjdToDate(primaryBtjd) });
      const secondaryBtjd = t0 + (e + secPhase) * period;
      if (secondaryBtjd > nowBtjd) out.push({ label: "Secondary", date: btjdToDate(secondaryBtjd) });
    }
    out.sort((a, b) => a.date.getTime() - b.date.getTime());
    return out.slice(0, 3);
  }, [d]);

  if (!d || events.length === 0) return null;

  return (
    <div className="rounded-lg border border-line bg-panel-2 p-3">
      <div className="nav-caps text-[11px] text-muted">Next eclipses (UTC)</div>
      <ul className="mt-2 space-y-1 text-xs">
        {events.map((ev, i) => (
          <li key={i} className="flex justify-between gap-3 font-mono text-fg">
            <span className="text-muted">{ev.label}</span>
            <span>{fmt(ev.date)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-faint">
        Computed from the fitted ephemeris. Approximate - not corrected for your location or for
        light-travel time across Earth&apos;s orbit.
      </p>
    </div>
  );
}
