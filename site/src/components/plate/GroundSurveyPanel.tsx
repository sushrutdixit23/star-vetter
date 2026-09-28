import type { GroundSurveyEntry } from "@/lib/types";

// Independent confirmation against real ZTF ground-survey photometry - a
// different instrument than TESS (Palomar's 48-inch Schmidt), spanning
// different years. Ground-survey cadence is sparse - a handful of epochs
// per orbit - so a periodogram built for smooth sinusoids finds essentially
// no power even on a real eclipse. The method instead folds at the
// TESS-measured period, flags individual epochs landing far below the
// baseline brightness, and tests whether the tightest pair of those flagged
// epochs is closer in phase than pure chance would produce given how many
// of them that band has (an exact circular-spacing significance test, not
// a fixed distance rule - see f12_ground_survey_period.py). Not finding a
// significant cluster does not count against a candidate - sparse cadence
// very often lands no epoch inside a narrow eclipse window at all, so this
// is supporting evidence when present, not a check every real binary is
// expected to pass.

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
  const strongest = confirmed
    .map(([band, b]) => ({ band, p: b.p_value }))
    .filter((x): x is { band: string; p: number } => typeof x.p === "number")
    .sort((a, b) => a.p - b.p)[0];

  const rows: [string, string][] = [
    ["Bands confirmed", confirmed.map(([band]) => BAND_LABEL[band] ?? band).join(", ")],
  ];
  if (deepest) rows.push(["Deepest clustered dip", `${deepest.sigma.toFixed(1)} sigma (${BAND_LABEL[deepest.band] ?? deepest.band})`]);
  if (strongest) rows.push(["Chance p-value", `${strongest.p < 0.0001 ? "< 0.0001" : strongest.p.toFixed(4)} (${BAND_LABEL[strongest.band] ?? strongest.band})`]);
  if (typeof g.period_days_tested === "number") rows.push(["Period tested", `${g.period_days_tested.toFixed(5)} d`]);

  return {
    kind: "pass",
    label: "Independently confirmed",
    note: `Real ZTF ground-survey photometry backs this period: ${confirmed.length === 1 ? "one band shows" : `${confirmed.length} bands show`} epochs, years apart, landing more than 5 sigma below the baseline brightness and clustered in phase far tighter than chance would produce given how many such epochs that band has (p < 0.01) - a different instrument finding the same eclipse.`,
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
              {BAND_LABEL[band] ?? band} <span className="text-faint">({b.n_points} pts, {b.n_outliers} outlier{b.n_outliers === 1 ? "" : "s"})</span>
            </span>
            <span className={b.verdict === "CONFIRMED" ? "text-emerald-300" : "text-faint"}>
              {b.verdict === "CONFIRMED"
                ? `Confirmed (p=${b.p_value !== null && b.p_value < 0.0001 ? "<0.0001" : b.p_value?.toFixed(4)})`
                : b.p_value !== null
                  ? `Not significant (p=${b.p_value.toFixed(2)})`
                  : "Too few outliers to test"}
            </span>
          </li>
        ))}
      </ul>
      {confirmedBands.length > 0 ? (
        <p className="text-sm leading-relaxed text-muted">
          Folded at the TESS-measured period of {period.toFixed(5)} d, {confirmedBands.length === bands.length ? "every band" : "at least one band"} shows individual ZTF epochs - real observations, years apart - landing far below the baseline brightness and clustered in phase far tighter than chance would produce given how many such epochs that band has (p &lt; 0.01, chance-corrected for the outlier count).
        </p>
      ) : (
        <p className="text-sm leading-relaxed text-muted">
          Folded at the TESS-measured period of {period.toFixed(5)} d, no band shows a phase cluster tight enough to rule out chance. Ground-survey cadence is sparse - a handful of epochs per orbit - so this is the expected outcome for most real eclipses, not evidence against this one.
        </p>
      )}
      <p className="text-[11px] text-faint">Source: ZTF public light-curve archive (IRSA), independent of the TESS data used to detect this candidate.</p>
    </div>
  );
}
