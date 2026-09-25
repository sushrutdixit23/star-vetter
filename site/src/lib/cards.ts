import type { Candidate } from "./types";
import type { CardData } from "@/components/CandidateCard";

export function toCardData(c: Candidate): CardData {
  return {
    tic: c.tic,
    tier: c.tier,
    period_days: c.ephemeris.period_days,
    corrected_period_days: c.ephemeris.aliased
      ? c.ephemeris.corrected_period_days
      : null,
    depth_frac: c.ephemeris.depth_frac,
    bls_snr: c.ephemeris.bls_snr,
    pixel_snr: c.pixel_check.diff_peak_snr,
    binned: c.light_curve.binned,
  };
}

// The period to quote for a star: the alias-corrected one when the pipeline
// flagged an alias, otherwise the BLS period.
export function bestPeriod(c: Candidate): number {
  return c.ephemeris.aliased && c.ephemeris.corrected_period_days !== null
    ? c.ephemeris.corrected_period_days
    : c.ephemeris.period_days;
}
