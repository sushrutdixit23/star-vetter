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

// ---------- ground_survey_period.json, written by f12_ground_survey_period.py:
// each confirmed candidate's TESS period, independently tested against real
// ZTF ground-survey photometry - a different instrument than TESS, spanning
// different years. ----------

export interface GroundSurveyClusteredPoint {
  phase: number;
  mag: number;
  sigma: number;
}

export interface GroundSurveyBand {
  n_points: number;
  baseline_mag: number;
  typical_err: number;
  n_outliers: number;
  // Chance-corrected significance of the tightest pair of outliers landing
  // as close as they did, given how many outliers this band has (exact
  // circular-spacing formula; see f12_ground_survey_period.py). null when
  // there weren't enough outliers to test. CONFIRMED requires p < 0.01.
  p_value: number | null;
  verdict: "CONFIRMED" | "NOT_CONFIRMED";
  clustered_points: GroundSurveyClusteredPoint[];
}

export interface GroundSurveyEntry {
  status: "CONFIRMED" | "NOT_CONFIRMED" | "NO_DATA" | "INSUFFICIENT_DATA" | "TIC_NOT_FOUND" | "ERROR";
  period_days_tested?: number;
  ra?: number;
  dec?: number;
  bands?: Record<string, GroundSurveyBand>;
  n_points_total?: number;
  error?: string;
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

// predictions.json is written by export_predictions.py from f13_ephemeris.py's
// output. Optional: the Predictions page and the candidate plates fall back to
// a "not published yet" message without it.
export type PredictionGrade = "VALIDATED" | "UNVALIDATED";

export interface PredictedEclipse {
  sector: number;
  cycle: number;
  t_btjd: number;
  utc: string; // "YYYY-MM-DD HH:MM:SS", geocentric UTC
  sigma_min: number;
  approximate: boolean; // sector dates are interpolated, not announced
  horizon_days: number | null; // days beyond the last measured eclipse
}

export interface PredictionStar {
  tic: number;
  tier: string;
  grade: PredictionGrade;
  tmag: number | null;
  ra: number | null;
  dec: number | null;
  depth_frac: number | null;
  ephemeris: {
    period_days: number;
    period_sigma_days: number;
    t0_btjd: number;
    n_eclipses: number;
    sectors_connected: number[];
    sectors_unconnected: number[];
    baseline_days: number;
    timing_jitter_min: number | null;
    timing_excess: boolean;
  };
  holdout: {
    status: string;
    sectors_tested: number | null;
    min_p_value: number | null;
    tested_reach_days: number | null; // furthest forward distance the hold-out predicted
    prediction_horizon_days: number | null; // nearest new prediction beyond the data
    extrapolation_factor: number | null; // horizon / tested reach
    grade_note: string;
  };
  novelty_extra: {
    verdict: string;
    matched_catalogs: string[];
    known_other_period: string[];
    nearby_catalogs: string[];
  } | null;
  best_sigma_min: number;
  predictions: PredictedEclipse[];
}

export interface PredictionsValidation {
  n_stars: number;
  median_abs_epoch_error_min: number | null;
  epoch_within_3sigma_fraction: number | null;
  period_z_robust_spread: number | null;
  source: string;
}

export interface HoldoutCalibration {
  n_stars: number;
  n_failed: number;
  failed_timing_scatter_min: number[];
  source: string;
}

export interface ExtraCatalogRecall {
  n_known_ebs: number;
  recall_period_match: number;
  recall_period_match_ci95: [number, number];
  recall_any_same_star: number;
  candidates_n: number;
  candidates_period_match_rate: number;
  source: string;
}

export interface PredictionsData {
  generated_utc: string;
  selection_rule: string[];
  max_sigma_min: number;
  conventions: Record<string, string>;
  counts: {
    candidates_considered: number;
    listed: number;
    listed_validated: number;
    listed_unvalidated: number;
    rejected_failed_holdout: number;
    status: Record<string, number>;
    holdout: Record<string, number>;
  };
  excluded: Record<string, number>;
  rejected: {
    tic: number;
    holdout_min_p_value: number | null;
    holdout_max_z_equiv: number | null;
    n_eclipses: number | null;
    baseline_days: number | null;
    grade_note: string;
  }[];
  validation: PredictionsValidation | null;
  holdout_calibration: HoldoutCalibration | null;
  extra_catalog_recall: ExtraCatalogRecall | null;
  stars: PredictionStar[];
}

// surface_evidence.json (export_surface_evidence.py): tidal / heating signals
// measured in each star's folded light curve. Drawn only where flagged.
export interface SurfaceStar {
  tides: boolean;
  heating: boolean;
  elongation: number;
  sinusoidal: boolean;
  ellipsoidal_amp?: number;
  ellipsoidal_err?: number;
  ellipsoidal_quadrature?: number;
  reflection_amp?: number;
  reflection_err?: number;
  frac_used?: number;
}

export interface SurfaceEvidence {
  thresholds: { min_snr: number };
  limits: string[];
  stars: Record<string, SurfaceStar>;
}

// surface_variability.json (export_surface_variability.py): starspot and flare
// tests on the full light curves. Each test is detected / none / not_tested.
export interface VariabilityTest {
  status: "detected" | "none" | "not_tested";
  reason?: string;
  cadence_min?: number;
  exposure_days?: number;
  n_candidates?: number;
  n_false_alarms?: number;
  n_tested?: number;
}

export interface SurfaceVariabilityStar {
  tested: boolean;
  reason?: string;
  spots_A?: VariabilityTest;
  spots_B?: VariabilityTest;
  flares?: VariabilityTest;
}

// novelty_extra.json (export_novelty_extra.py): the six-catalog cross-match
// verdict for every candidate. ALREADY_KNOWN = same star, same period.
export interface NoveltyExtra {
  verdict: string;
  matched_catalogs: string[];
  known_other_period: string[];
  nearby_catalogs: string[];
}

// audit.json (export_audit.py): the funnel of the Kostov et al. 2025 unvetted
// list with stratified rates and 95% intervals.
export interface RateInterval {
  k: number;
  n: number;
  rate: number | null;
  lo: number;
  hi: number;
}
export interface MedianInterval {
  median: number;
  lo: number;
  hi: number;
}
export interface AuditStratum {
  stratum: number;
  label: string;
  population: number;
  weight: number;
  sampled: number;
  usable: number;
  passed_gates: number;
  novel: number;
  on_target: number;
  usable_rate: RateInterval;
  passed_per_usable: RateInterval;
  on_target_per_usable: RateInterval;
}
export interface AuditData {
  generated_at: string;
  frame: { list: string; population: number; sampled: number; sampled_fraction: number; design: string; intervals: string };
  funnel: { key: string; label: string; count: number }[];
  strata: AuditStratum[];
  rates: Record<string, MedianInterval>;
  recall: { source: string; recovered: number; usable: number; sampled: number; given_usable: RateInterval };
  provisional_correction: {
    label: string; value: MedianInterval; assumption: string;
    with_quiet_host_recall?: { recall: RateInterval; value: MedianInterval; note: string };
    with_injection_recall?: { recall: RateInterval; value: MedianInterval; consistent_with_benchmark: boolean; note: string };
  } | null;
  periods: { bin: string; passed: number; on_target: number }[];
  notes: string[];
}

// recovery.json (injection_recovery.py): synthetic binaries injected into real
// light curves and run through the real gates.
export interface RecoveryCell {
  n: number;
  detected: RateInterval;
  exact_period: RateInterval;
  bin?: string;
  stratum?: number;
}
export interface RecoveryData {
  generated_at: string;
  counts: { stars: number; injections: number; searchable_injections: number; shuffle_runs: number };
  searchable_fraction: RateInterval;
  recall_overall: RecoveryCell;
  recall_by_tmag_stratum: RecoveryCell[];
  recall_by_period: RecoveryCell[];
  recall_by_depth: RecoveryCell[];
  recall_by_points_per_eclipse: RecoveryCell[];
  miss_reasons: { gate: string; missed_flagged: RateInterval }[];
  missed_on_host_signal?: RateInterval | null;
  passed_with_unrelated_period: RateInterval;
  false_alarm_shuffle: RateInterval;
  method: { gates: string; stars: string; recovery: string; shuffle: string; not_tested: string[] };
  notes: string[];
}

// atlas_alias.json (f14b_atlas_alias.py)
export interface AtlasAliasData {
  tested: number;
  atlas_class_of_tested: Record<string, number>;
  explained: { k: number; n: number; harmonic_only: number; with_sidereal: number };
  chance: { pair_rate: number; expected_explained: number; p_value_at_least_observed: number | null };
  already_matching_ratio_1_half_2: number;
  method: { relation: string; hypotheses: number; tolerance_basis: string };
  reading: string;
}

// neighbours.json (f15_neighbours.py)
export interface NeighbourStar {
  offset_arcsec: number;
  diff_snr: number;
  n_neighbours: number;
  status: "NO_VIABLE_NEIGHBOUR" | "UNSEPARABLE_NEIGHBOUR" | "VIABLE_NEIGHBOUR_AT_OFFSET";
  viable: number;
  closest_viable: { tic: number; sep_arcsec: number; delta_tmag: number; required_depth: number } | null;
}
export interface NeighboursData {
  stars_assessed: number;
  summary_by_floor: Record<string, Record<string, number>>;
  method: { headline_floor_arcsec: number; centroid_floors_arcsec: number[]; assumptions: string; not_covered: string };
  statuses: Record<string, string>;
  stars: Record<string, NeighbourStar>;
}


// evidence.json (f20_evidence.py)
export type EvidenceTier = "INDEPENDENTLY_SUPPORTED" | "TESS_ONLY_CLEAN" | "TESS_ONLY_CAVEATS" | "DISFAVOURED";
export type NoveltyLabel = "KNOWN_ECLIPSING" | "KNOWN_BINARY" | "KNOWN_VARIABLE" | "NO_PRIOR_FOUND";
export interface EvidenceStar {
  evidence_tier: EvidenceTier;
  independent_lines: string[];
  against: string[];
  caveats: string[];
  novelty: NoveltyLabel;
  novelty_reasons: string[];
  ztf_status: string;
  gaia_period_relation: string | null;
}
export interface EvidenceData {
  generated_at: string;
  summary: {
    stars: number;
    by_evidence_tier: Record<string, number>;
    by_novelty: Record<string, number>;
    tier_by_novelty: Record<string, number>;
    by_ztf_status: Record<string, number>;
  };
  definitions: Record<string, string>;
  stars: Record<string, EvidenceStar>;
}

// ztf_independent.json (f17_ztf_independent.py, export_independent.py)
export interface ZtfData {
  generated_at: string;
  summary: {
    stars: number;
    by_status: Record<string, number>;
    testable: number;
    confirmed_among_testable: RateInterval;
    confirmed_among_with_data: RateInterval;
    by_tier: Record<string, Record<string, number>>;
  };
  method: Record<string, string>;
}

// gaia_dr3.json (f18_gaia_dr3.py)
export interface GaiaData {
  generated_at: string;
  data_release: string;
  summary: {
    stars: number; matched: number; ambiguous: number; none: number; ruwe_elevated: number;
    contamination_status_gaia: Record<string, number>;
    in_gaia_eb_table: number; in_gaia_nss_orbit: number; with_gaia_rv: number; rv_variable: number;
  };
  method: { match: string; contamination: string; dr4: string };
}

// prior_art.json (f19_prior_art.py)
export interface PriorArtData {
  generated_at: string;
  sources: { name: string; id: string; what: string; status: "CHECKED" | "NOT_CHECKED"; reason?: string; rows?: number; matches?: number }[];
  summary: { stars: number; in_any_new_catalog: number; on_toi_list: number; simbad_identified: number; simbad_groups: Record<string, number> };
  note: string;
}

// gaia_dr4_plan.json (f21_gaia_dr4_ready.py)
export interface GaiaDr4Plan {
  release: string;
  criterion: string;
  stars_with_precise_ephemeris: number;
  testable: number;
}

// preregistration.json: where the frozen predictions were deposited. Written by
// hand from the freeze manifest and the Zenodo record (see docs/publication_readiness.md).
export interface Preregistration {
  doi: string;
  url: string;
  deposited_utc: string;
  frozen_utc: string;
  bundle_sha256: string;
  commit: string;
  branch: string;
  stars: number;
  eclipses: number;
  file: string;
  repo: string;
}


export interface EccentricCandidate {
  tic: number;
  period_days: number;
  ecosw: number;
  ecosw_sigma: number;
  secondary_phase: number;
  secondary_depth: number;
  secondary_snr: number;
  marginal: boolean;
  ztf_coverage: string | null;
  ztf_confirmed: boolean | null;
  ztf_p_value: number | null;
  evidence_tier: string | null;
  novelty: string | null;
}

export interface PeriodChangeStar {
  tic: number;
  period_days: number;
  n_tess: number;
  n_ztf: number;
  chi2_line: number;
  dof_line: number;
  chi2_parabola: number;
  dof_parabola: number;
  dP_dt_seconds_per_year: number;
  dP_dt_sigma_seconds_per_year: number;
}

export interface FindingsData {
  generated_at: string;
  verdict_counts: Record<string, number>;
  candidates: EccentricCandidate[];
  period_bins: { p_min: number; p_max: number; n_measured: number; n_offset: number }[];
  circularisation: {
    threshold_ecosw: number;
    n_short: number;
    k_short: number;
    n_longer: number;
    k_longer: number;
    chance_of_none_if_same_rate_as_longer: number | null;
  };
  timing_drift: {
    counts: Record<string, number>;
    period_change: PeriodChangeStar[];
    calibration: { trials: number; flagged: number } | null;
  } | null;
  limits: string[];
}

export interface PeriodChangePredictions {
  rule: string;
  time_system: string;
  stars: Record<string, {
    tic: number;
    period_days: number;
    predictions: { epoch: number; bjd_tdb_parabola: number; sigma_min: number }[];
  }>;
}
