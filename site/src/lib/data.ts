import fs from "fs";
import path from "path";
import type {
  AboutContent,
  Candidate,
  Dashboard,
  Detail,
  ModelMetrics,
  PipelineStats,
  SiteIndex,
  SiteMeta,
} from "./types";
import type { Summary } from "@/components/dash/DetailPanels";

// Reads the JSON export_site_data.py writes into public/data/ - this runs
// server-side at build/request time, so the site never needs its own
// database or API: the pipeline's own output files are the data source.

const DATA_DIR = path.join(process.cwd(), "public", "data");

export function getIndex(): SiteIndex {
  const raw = fs.readFileSync(path.join(DATA_DIR, "index.json"), "utf-8");
  return JSON.parse(raw) as SiteIndex;
}

export function getAllTics(): number[] {
  return getIndex().candidates.map((c) => c.tic);
}

export function getCandidate(tic: number): Candidate {
  const raw = fs.readFileSync(
    path.join(DATA_DIR, "candidates", `TIC${tic}.json`),
    "utf-8"
  );
  return JSON.parse(raw) as Candidate;
}

// pipeline_stats.json is written by export_pipeline_stats.py, which reads
// the pipeline's own on-disk CSVs. Optional: the About page still renders
// (without the funnel) if this hasn't been generated yet.
export function getPipelineStats(): PipelineStats | null {
  const p = path.join(DATA_DIR, "pipeline_stats.json");
  if (!fs.existsSync(p)) return null;
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw) as PipelineStats;
}

// model_metrics.json is written by f7b_train_classifier.py / export_model_
// metrics.py - the ML screening model's cross-validated metrics against the
// rule baseline. Optional: the About page's ML section just doesn't render
// without it, same pattern as pipeline_stats.json.
export function getModelMetrics(): ModelMetrics | null {
  const p = path.join(DATA_DIR, "model_metrics.json");
  if (!fs.existsSync(p)) return null;
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw) as ModelMetrics;
}

// about_content.json is written by f9_generate_about_content.py - a batch-
// generated (not per-visitor) narrative paragraph and FAQ list for the
// About page, grounded in the pipeline's own numbers. Optional, same
// pattern as pipeline_stats.json and model_metrics.json.
export function getAboutContent(): AboutContent | null {
  const p = path.join(DATA_DIR, "about_content.json");
  if (!fs.existsSync(p)) return null;
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw) as AboutContent;
}

// site_meta.json is written by export_extras.py (last orchestrator run time,
// which dossier PDFs were copied in). Optional, like pipeline_stats.json.
export function getSiteMeta(): SiteMeta | null {
  const p = path.join(DATA_DIR, "site_meta.json");
  if (!fs.existsSync(p)) return null;
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw) as SiteMeta;
}

export function getAllCandidates(): Candidate[] {
  return getAllTics().map((t) => getCandidate(t));
}

// dashboard.json and detail/TIC{n}.json are written by export_dashboard.py.
// Both optional: the home page falls back to the basic panels without them.
export function getDashboard(): Dashboard | null {
  const p = path.join(DATA_DIR, "dashboard.json");
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf-8")) as Dashboard;
}

export function getDetail(tic: number): Detail | null {
  const p = path.join(DATA_DIR, "detail", `TIC${tic}.json`);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf-8")) as Detail;
}

// The one place a Candidate (export_site_data.py's shape) becomes a Summary
// (what every dashboard panel actually reads). Shared by the home page's
// Explorer and the standalone /candidates/[tic] page so both render the
// exact same view of a given star - no second, drifting definition.
export function toSummary(c: Candidate): Summary {
  return {
    tic: c.tic,
    tier: c.tier,
    caveats: c.caveats,
    period_days: c.ephemeris.period_days,
    corrected_period_days: c.ephemeris.aliased ? c.ephemeris.corrected_period_days : null,
    aliased: c.ephemeris.aliased,
    depth_frac: c.ephemeris.depth_frac,
    duration_days: c.ephemeris.duration_days,
    bls_snr: c.ephemeris.bls_snr,
    odd_even_z: c.gates.odd_even_z,
    pixel: {
      sector: c.pixel_check.sector,
      diff_peak_snr: c.pixel_check.diff_peak_snr,
      centroid_offset_px: c.pixel_check.centroid_offset_px,
      centroid_offset_arcsec: c.pixel_check.centroid_offset_arcsec,
      t0_shift_phase: c.pixel_check.t0_shift_phase,
      compactness: c.pixel_check.compactness,
      nearest: c.pixel_check.nearest_neighbour,
      image: c.pixel_check.image,
    },
    catalogs: c.novelty.catalogs,
    binned: c.light_curve.binned,
  };
}