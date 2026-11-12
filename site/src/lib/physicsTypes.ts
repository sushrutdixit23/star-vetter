// Types for site/public/data/physics.json (written by export_physics.py). Kept free of Node imports so
// client components can use them.

import type { PhysicalFit } from "./types";

export interface BestFit {
  rsum: number;
  k: number;
  incl: number;
  J: number;
  e: number;
  omega_deg: number;
  l3: number;
}

export interface CurveSet {
  period_days: number;
  t0_btjd: number;
  cadence_min: number;
  n_display_bins: number;
  n_fit_bins: number;
  sectors: number[];
  duration_phase: number;
  best_fit: BestFit;
  secondary_phase_kepler: number;
  secondary_phase_ellc: number | null;
  min_flux: number;
  rms_resid_ppt: number;
  data: { x: number[]; y: number[]; e: number[] };
  residual: number[];
  model: { x: number[]; y: number[] };
}

export interface StarCurve extends CurveSet {
  tic: number;
  depth_pct: number | null;
}

export interface AiPheCurve extends CurveSet {
  published_model: { x: number[]; y: number[] };
  truth: Record<string, number>;
  fit_summary: Record<string, number>;
  checks: Record<string, boolean>;
  passed: boolean;
  reference: string;
  tolerance?: Record<string, number>;
  published_refit?: { model: { x: number[]; y: number[] }; rms_resid_ppt: number; chi2: number; chi2_ours: number; n_bins: number; J: number; l3: number; refitted: string[] };
  cadence30?: { fit: Record<string, number>; checks: Record<string, boolean>; passed: boolean };
}

export interface RvPoint {
  tic: number;
  period_days: number;
  depth_pct: number;
  rv_range_kms: number;
  k1_lower_kms: number;
  n_transits: number;
  verdict: string;
}

export interface MassPoint {
  tic: number;
  ratio: number;
  rel_sigma: number;
  consistent: boolean;
  basis: string | null;
}

export interface PhysicsData {
  generated_at: string;
  note: string;
  stars: Record<string, StarCurve>;
  ai_phe: AiPheCurve;
  rv_population: RvPoint[];
  mass_check_points: MassPoint[];
  benchmarks?: Benchmarks;
  injection?: Injection;
  convergence?: ConvergenceRow[];
  mass_calibration?: MassCalibration;
}

export interface Q3 {
  median: number;
  lo: number;
  hi: number;
}

export interface BenchmarkRow {
  name: string;
  tic: number;
  cadence_min: number;
  status: string;
  passed: boolean;
  reference: string;
  truth: Record<string, number>;
  checks?: Record<string, boolean>;
  differences?: Record<string, number>;
  fit?: Record<string, Q3>;
  trusted?: boolean;
  converged?: boolean;
  steps?: number;
  f22_verdict?: string | null;
}

export interface Benchmarks {
  rows: BenchmarkRow[];
  pass_rule: Record<string, number | string>;
  summary: { runs: number; passed: number; systems_passing_both_cadences: string[] };
  preregistration: string;
}

export interface QuantityMetrics {
  /** How many times wider the quoted 68% interval would have to be for 68% of injections to fall inside it. */
  error_inflation_68?: number | null;
  median_error: number | null;
  median_abs_error: number | null;
  median_abs_fractional_error: number | null;
  coverage_68: number | null;
  coverage_95: number | null;
}

export interface InjectionMetrics {
  n_injected: number;
  n_fitted: number;
  by_quantity: Record<string, QuantityMetrics>;
  trust_rule: {
    accepted: number;
    rejected: number;
    accepted_good_fraction: number | null;
    rejected_good_fraction: number | null;
    largest_rsum_threshold_with_80pc_good: { rsum_max: number; n_accepted: number; good_fraction: number } | null;
  };
  /** Added after the first results: how often the fitted |e cos w| (the "lower limit on e") exceeded the injected e. */
  ecosw_lower_limit?: { n_checked: number; violations: number; rule: string; violations_untrusted: number };
}

export interface InjectionPoint {
  host: number;
  i: number;
  trusted: boolean;
  converged: boolean;
  t: Record<string, number>;
  f: Record<string, Q3>;
  rsum_fit: number;
}

export interface Injection {
  overall: InjectionMetrics;
  by_host: Record<string, InjectionMetrics>;
  by_true_rsum?: Record<string, InjectionMetrics>;
  points: InjectionPoint[];
  e_good_definition: string;
  n_rows: number;
}

export interface ConvergenceRow {
  tic: number;
  before: Q3;
  after: Q3;
  steps_before: number;
  steps_after: number;
  converged_after: boolean;
  tau_after: number;
  rsum_after: number;
}

export interface MassCalibrationRow {
  name: string;
  status: string;
  R1_ratio?: number;
  mass_ratio?: number;
  gaia_radius_flame?: number;
  R1_from_gaia?: number;
  kepler_mass_from_gaia?: number;
  published_total_mass?: number;
  ruwe?: number;
  non_single_star?: number;
  ms_ratio_gaia?: number | null;
  ms_ratio_true?: number | null;
  published?: Record<string, number>;
}

export interface MassCalibration {
  rows: MassCalibrationRow[];
  summary: { n: number; median_R1_ratio: number | null; median_mass_ratio: number | null };
}

/** One star as the Orbit Studio needs it: its curves, its fit, and whatever Gaia says about it. */
export interface StudioStar {
  tic: number;
  curve: StarCurve;
  fit: PhysicalFit;
  gaia: { type: string; period_days: number; period_ratio: number; same_period: boolean; outer: boolean; k1_kms: number | null } | null;
  rv: { verdict: string; range_kms: number; n_transits: number } | null;
  ecc_check: { gaia_e: number; gaia_e_sigma: number; fit_e: number; diff_sigma: number; trusted: boolean } | null;
}
