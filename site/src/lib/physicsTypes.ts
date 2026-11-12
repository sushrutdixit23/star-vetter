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
