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

export interface CatalogProgress {
  total_catalog: number;
  sampled_to_date: number;
  fraction: number;
}

export interface PipelineStats {
  funnel: FunnelStep[];
  catalog_progress: CatalogProgress | null;
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

// ---------- ML screening model (written by f7b_train_classifier.py /
// export_model_metrics.py, scored per-candidate by f7c_score_candidates.py,
// joined into detail/TIC{n}.json by export_dashboard.py) ----------
//
// This is a second opinion, not a gate: nothing in the pipeline currently
// uses ml_score to skip a pixel check. It is cross-validated on the
// pipeline's own labeled history and reported honestly either way, win or
// lose against the rule baseline - see model_metrics.json / the About page.

export interface ModelMetricEntry {
  precision_mean: number;
  precision_std: number;
  recall_mean: number;
  recall_std: number;
  roc_auc_mean: number;
  roc_auc_std: number;
  average_precision_mean: number;
  average_precision_std: number;
}

export interface ScreeningValueRow {
  target_recall: number;
  threshold: number;
  recall: number;
  fraction_screened_out: number;
}

export interface FeatureImportanceRow {
  feature: string;
  importance_mean: number;
}

export interface ModelMetrics {
  generated_at: string;
  trained_at: string;
  n_training_samples: number;
  n_training_positive: number;
  n_training_negative: number;
  n_cv_folds: number;
  baseline: {
    description: string;
    recall: number;
    precision: number;
  };
  models: Record<string, ModelMetricEntry>;
  chosen_model: string;
  beats_baseline: boolean;
  screening_value: ScreeningValueRow[];
  feature_importance: FeatureImportanceRow[];
  total_scored_this_run?: number;
  pending_pixel_check?: number;
  note?: string;
}

// ---------- About page narrative + FAQ (written by
// f9_generate_about_content.py) ----------
//
// A one-time batch generation, not per-visitor: grounded in the pipeline's
// own numbers (index.json / model_metrics.json / pipeline_stats.json) and
// cached to about_content.json. Optional, same pattern as ModelMetrics -
// the About page's plain-English and FAQ sections just don't render
// without it.

export interface AboutFaq {
  question: string;
  answer: string;
}

export interface AboutContent {
  narrative: string;
  faqs: AboutFaq[];
  model: string;
  generated_at: string;
}

// ---------- Discoveries showcase (written by
// f10_generate_discoveries.py) ----------
//
// A handful of standout candidates picked by real, objective criteria the
// pipeline already computed (deepest eclipse, highest ML score, and so
// on), with a short AI-written blurb per pick explaining why it stands out
// - grounded strictly in that candidate's own numbers. One batch call, not
// per-visitor, cached to discoveries.json. Optional, same pattern as
// AboutContent - the Discoveries page just says there is nothing yet
// without it.

export interface Discovery {
  tic: number;
  category: string;
  category_label: string;
  stat_text: string;
  headline: string;
  blurb: string;
}

export interface DiscoveriesData {
  discoveries: Discovery[];
  model: string;
  generated_at: string;
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
  ml_score: number | null;
  ml_model_name: string | null;
  writeup: string | null;
}

// ---------- raw per-candidate time series (optional; written by a
// timeseries export script that does not exist yet). This is the un-folded
// BJD/flux data "fold it yourself" needs to re-fold at an arbitrary trial
// period - Detail.fold.raw is already folded at the true period, so it
// cannot be reused for that. getTimeseries() returns null until this file
// exists; the UI shows a placeholder until then. ----------

export interface Timeseries {
  tic: number;
  bjd: number[];
  flux: number[];
}

// ---------- Gaia DR3 context per candidate (gaia_context.json, keyed by
// TIC as a string). gaia_source_id is read as a string: the ids exceed
// JavaScript's safe integer range. ----------

export interface GaiaContext {
  status: string;
  gaia_source_id: string | null;
  separation_arcsec: number | null;
  phot_g_mean_mag: number | null;
  bp_rp: number | null;
  parallax_mas: number | null;
  parallax_error_mas: number | null;
  parallax_snr?: number | null;
  distance_pc: number | null;
  distance_reliable: boolean;
  abs_g_mag?: number | null;
  ruwe: number | null;
  elevated_ruwe?: boolean;
  note?: string;
}

// ---------- benchmark.json, written by benchmark_report.py: known eclipsing
// binaries run blind through the unmodified pipeline. ----------

export interface BenchmarkCount {
  key: string;
  count: number;
}

export interface BenchmarkStar {
  tic: number;
  tmag: number | null;
  true_period_days: number | null;
  stage: string;
  outcome: string;
  recovered: boolean;
  gates: string[];
}

export interface BenchmarkControl {
  TIC?: number | null;
  role?: string | null;
  verdict?: string | null;
  expected?: string | null;
  expected_verdict?: string | null;
  note?: string | null;
  reason?: string | null;
}

export interface Benchmark {
  generated_at: string;
  sample: { source: string; n: number; selection: string };
  definition: string;
  controls_note: string;
  funnel: { label: string; count: number }[];
  recall: { recovered: number; sampled: number };
  fetch_status: BenchmarkCount[];
  gates: { gate: string; label: string; count: number }[];
  novelty: BenchmarkCount[];
  pixel: BenchmarkCount[];
  too_few_eclipses: { n_flagged: number; median_period_flagged: number | null; n_rest: number; median_period_rest: number | null } | null;
  by_tmag: { bin: string; recovered: number; n: number }[];
  controls: BenchmarkControl[];
  stars: BenchmarkStar[];
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