export type Tier =
  | "CLEAN"
  | "MARGINAL"
  | "AMBIGUOUS PHOTOMETRY"
  | "THIN MARGIN"
  | "PERIOD ALIAS";

export interface IndexRow {
  tic: number;
  tier: Tier;
  period_days: number;
  depth_frac: number;
  bls_snr: number;
  pixel_snr: number;
  offset_arcsec: number;
}

export interface SiteIndex {
  generated_stats: {
    n_confirmed: number;
    n_pixel_checked: number;
  };
  candidates: IndexRow[];
}

export interface Caveat {
  tier: Tier;
  text: string;
}

export interface Ephemeris {
  period_days: number;
  corrected_period_days: number | null;
  aliased: boolean;
  t0_btjd: number;
  duration_days: number;
  depth_frac: number;
  depth_ppm: number;
  bls_snr: number;
}

export interface Gates {
  eclipses_observed: number;
  depth_ratio: number;
  robust_sigma: number;
  odd_even_z: number;
  secondary_detected: boolean;
  secondary_phase: number | null;
  secondary_sigma: number | null;
}

export interface CatalogCheck {
  name: string;
  matched: boolean;
}

export interface Novelty {
  verdict: string;
  catalogs: CatalogCheck[];
}

export interface NearestNeighbour {
  tic: number;
  dist_px: number;
  dtmag: number;
}

export interface PixelCheck {
  sector: number;
  lc_dip_sigma: number;
  t0_shift_phase: number;
  diff_peak_snr: number;
  compactness: number;
  centroid_offset_px: number;
  centroid_offset_arcsec: number;
  nearest_neighbour: NearestNeighbour | null;
  image: string;
}

export interface LightCurve {
  raw: [number, number][];
  binned: [number, number | null][];
}

export interface FunnelStep {
  label: string;
  count: number;
}

export interface GateInfo {
  name: string;
  text: string;
}

export interface PipelineStats {
  funnel: FunnelStep[];
  catalogs: string[];
  vetting_gates: GateInfo[];
  pixel_gates: GateInfo[];
}

export interface LastRun {
  iso: string;
  display: string;
  log_file: string;
}

export interface SiteMeta {
  last_run: LastRun | null;
  runs_logged: number;
  dossiers_available: number[];
  combined_dossier: string | null;
}

export interface Candidate {
  tic: number;
  tier: Tier;
  caveats: Caveat[];
  ephemeris: Ephemeris;
  gates: Gates;
  novelty: Novelty;
  pixel_check: PixelCheck;
  light_curve: LightCurve;
}

// ---------- dashboard data (written by export_dashboard.py) ----------

export type XY = [number, number];

export interface DepthMeasure {
  depth: number;
  err: number;
  sigma: number | null;
  n_core: number;
}

export interface SecondaryMeasure extends DepthMeasure {
  phase: number;
  detected: boolean;
}

export interface CatalogInfo {
  ra?: number | null;
  dec?: number | null;
  tmag?: number | null;
  gaia_g?: number | null;
  dist_pc?: number | null;
  dist_err_pc?: number | null;
  teff_k?: number | null;
  radius_rsun?: number | null;
  gaia_id?: string | null;
}

export interface FoldData {
  binned: XY[];
  raw: XY[];
}

export interface ZoomData {
  raw: XY[];
  binned: XY[];
  half_width_h: number;
}

export interface TimingPoint {
  epoch: number;
  oc_min: number | null;
  err_min: number;
}

export interface Timing {
  points: TimingPoint[];
  n: number;
  note?: string;
  period_fit_days?: number;
  period_fit_err_days?: number;
  rms_min?: number;
  chi2_red?: number | null;
  dof?: number;
}

export interface Neighbour {
  tic: number;
  x: number;
  y: number;
  tmag: number;
  capable: boolean;
}

export interface PixelMaps {
  tic: number;
  sector: number;
  out: (number | null)[][];
  diff: (number | null)[][];
  snr: (number | null)[][];
  target: XY;
  centroid: XY;
  neighbours: Neighbour[];
}

export interface Detail {
  tic: number;
  period_true_days: number;
  period_bls_days: number;
  aliased: boolean;
  t0_btjd: number;
  duration_days: number;
  baseline_days: number;
  n_points: number;
  odd_even_z: number | null;
  depth_odd: number | null;
  depth_even: number | null;
  primary: DepthMeasure | null;
  secondary: SecondaryMeasure | null;
  periodicity: {
    ls_period_days: number;
    ls_power: number;
    ratio: number;
    flag: boolean;
    text?: string;
  } | null;
  checks: string[];
  epochs: {
    covered: number;
    seen: number;
    absent: number;
    rows: {
      epoch: number;
      t_mid: number;
      depth: number | null;
      err: number | null;
      sigma: number | null;
      seen: boolean;
      absent: boolean;
    }[];
  };
  catalog: CatalogInfo;
  fold: FoldData & { resid: XY[]; resid_rms: number | null; second_phase: number };
  alias: { bls: FoldData; double: FoldData };
  zoom: { primary: ZoomData | null; secondary: ZoomData | null };
  timing: Timing;
  pixel_maps: PixelMaps | null;
}

export interface SkyPoint {
  tic: number;
  tier: Tier;
  ra: number | null;
  dec: number | null;
  period_days: number;
  bls_snr: number;
}

export interface RunInfo {
  id: string;
  log_file: string;
  started: string | null;
  finished: string | null;
  runtime_min: number | null;
  status: string;
  targets_drawn: number | null;
  fetched: number | null;
  confirmed_total: number | null;
  stage_failures: number;
  retries: number;
}

export interface ActivityEvent {
  kind: "ok" | "fail" | "decision";
  stage: string;
  text: string;
}

export interface Dashboard {
  sky: SkyPoint[];
  runs: RunInfo[];
  activity: ActivityEvent[];
  activity_log: string | null;
}
