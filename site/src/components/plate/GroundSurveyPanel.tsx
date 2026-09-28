import type { GroundSurveyEntry } from "@/lib/types";

// Independent confirmation against real ZTF ground-survey photometry - a
// different instrument than TESS (Palomar's 48-inch Schmidt), spanning
// different years. Ground-survey cadence is sparse - a handful of epochs
// per orbit - so a periodogram built for smooth sinusoids finds essentially
// no power even on a real eclipse. The method instead folds at the
// TESS-measured period and looks for individual epochs landing far below
// the baseline brightness, clustered at a consistent phase: something
// noise does not do twice. Not finding a cluster does not count against a
// candidate - sparse cadence very often lands no epoch inside a narrow
// eclipse window at all, so this is supporting evidence when present, not
// a check every real binary is expected to pass.

const BAND_LABEL: Record<string, string> = { zg: "ZTF g", zr: "ZTF r", zi: "ZTF i" };

export interface GroundSurveyVerdict {
  kind: "pass";
  label: string;
  note: string;
  rows: [string, string][];
}

export function groundSurveyVerdict(g: GroundSurveyEntry | null): GroundSurveyVerdict | null {
  if (!g || g.status !== "CONFIRMED" || !g.bands) return null;
  const confirmed = Object.entries(g.bands).filter(([, b]) => b.verdict === "CONFIRMED");
  if (confirmed.length === 0) return null;

  const deepest = confirmed
    .flatMap(([band, b]) => b.clustered_points.map((p) => ({ band, sigma: p.sigma })))
    .sort((a, b) => b.sigma - a.sigma)[0];

  const rows: [string, string][] = [
    ["Bands confirmed", confirmed.map(([band]) => BAND_LABEL[band] ?? band).join(", ")],
  ];
  if (deepest) rows.push(["Deepest clustered dip", `${deepest.sigma.toFixed(1)} sigma (${BAND_LABEL[deepest.band] ?? deepest.band})`]);
  if (typeof g.period_days_tested === "number") rows.push(["Period tested", `${g.period_days_tested.toFixed(5)} d`]);

  return {
    kind: "pass",
    label: "Independently confirmed",
    note: `Real ZTF ground-survey photometry backs this period: ${confirmed.length === 1 ? "one band shows" : `${confirmed.length} bands show`} at least two epochs, years apart, clustered within the same narrow phase window and each more than 5 sigma below the baseline brightness - a different instrument finding the same eclipse.`,
    rows,
  };
}

export default function GroundSurveyPanel({ g }: { g: GroundSurveyEntry | null }) {
  if (!g) {
    return <p className="text-sm text-muted">The latest ground-survey file does not include this candidate yet, so there is no independent ZTF check to show.</p>;
  }

  if (g.status === "NO_DATA") {
    return (
      <p className="text-sm leading-relaxed text-muted">
        No ZTF observations at this position{typeof g.dec === "number" ? ` (declination ${g.dec.toFixed(1)} deg)` : ""} - likely too far south for ZTF&apos;s footprint, which covers the sky north of roughly -31 deg. Not a mark against the candidate, just a gap in ground-survey coverage.
      </p>
    );
  }

  if (g.status === "INSUFFICIENT_DATA") {
    return (
      <p className="text-sm leading-relaxed text-muted">
        ZTF has observed this position, but only {g.n_points_total ?? "a few"} good points total - not enough in any single band to test for a clustered eclipse signal.
      </p>
    );
  }

  if (g.status === "TIC_NOT_FOUND" || g.status === "ERROR" || !g.bands) {
    return <p className="text-sm text-muted">This check could not be completed for this candidate yet.</p>;
  }

  const bands = Object.entries(g.bands);
  const confirmedBands = bands.filter(([, b]) => b.verdict === "CONFIRMED");
  const period = g.period_days_tested ?? 0;

  return (
    <div className="space-y-4">
      <ul className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        {bands.map(([band, b]) => (
          <li key={band} className="flex items-center justify-between gap-2 border-b border-line py-1.5 text-[11px]">
            <span className="text-fg">
              {BAND_LABEL[band] ?? band} <span className="text-faint">({b.n_points} pts)</span>
            </span>
            <span className={b.verdict === "CONFIRMED" ? "text-emerald-300" : "text-faint"}>
              {b.verdict === "CONFIRMED" ? `Confirmed (${b.clustered_points.length} clustered)` : "No cluster found"}
            </span>
          </li>
        ))}
      </ul>
      {confirmedBands.length > 0 ? (
        <p className="text-sm leading-relaxed text-muted">
          Folded at the TESS-measured period of {period.toFixed(5)} d, {confirmedBands.length === bands.length ? "every band" : "at least one band"} shows individual ZTF epochs - real observations, years apart - landing far below the baseline brightness at a consistent orbital phase. Two independent epochs agreeing to within a few percent of the orbit is not something noise does.
        </p>
      ) : (
        <p className="text-sm leading-relaxed text-muted">
          Folded at the TESS-measured period of {period.toFixed(5)} d, no band shows a clustered group of deep outliers. Ground-survey cadence is sparse - a handful of epochs per orbit - so this is the expected outcome for most real eclipses, not evidence against this one.
        </p>
      )}
      <p className="text-[11px] text-faint">Source: ZTF public light-curve archive (IRSA), independent of the TESS data used to detect this candidate.</p>
    </div>
  );
}
