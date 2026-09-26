import Link from "next/link";
import {
  getAllCandidates,
  getDashboard,
  getDetail,
  getPipelineStats,
  getSiteMeta,
  toSummary,
} from "@/lib/data";
import { TIER_STYLE } from "@/lib/tiers";
import Panel from "@/components/Panel";
import Starfield from "@/components/Starfield";
import SkyMap from "@/components/dash/SkyMap";
import PipelineStages from "@/components/dash/PipelineStages";
import { ActivityFeed, LatestRun, RunsTable } from "@/components/dash/RunPanels";
import Explorer from "@/components/dash/Explorer";
import type { Summary } from "@/components/dash/DetailPanels";
import { IconArrow } from "@/components/icons";
import WhatIsThis from "@/components/WhatIsThis";

const SHORT: Record<string, string> = {
  "Targets sampled and fetch attempted": "targets sampled",
  "Usable light curve obtained": "usable light curves",
  "Passed statistical vetting gates": "statistically passing",
  "Flagged novel (no catalog match)": "novel (catalog-unique)",
  "Survived contamination check, pixel-checked": "pixel-checked",
  "Confirmed on-target": "confirmed on-target",
};

export default function Home() {
  const stats = getPipelineStats();
  const meta = getSiteMeta();
  const dash = getDashboard();
  const candidates = getAllCandidates().sort((a, b) => b.ephemeris.bls_snr - a.ephemeris.bls_snr);
  const featured = candidates[0];
  const featuredDetail = getDetail(featured.tic);
  const funnel = stats?.funnel ?? [];
  const total = funnel.length > 0 ? funnel[0].count : 0;

  const summaries: Summary[] = candidates.map(toSummary);

  const P = featuredDetail
    ? featuredDetail.period_true_days
    : featured.ephemeris.corrected_period_days ?? featured.ephemeris.period_days;
  const latest = dash?.runs[0] ?? null;

  return (
    <main className="mx-auto w-full max-w-[1920px] flex-1 space-y-4 px-3 py-4 sm:px-6">
      {/* ---------- hero | pipeline + latest run ---------- */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <section className="relative overflow-hidden rounded-xl border border-line bg-[#05070c] xl:col-span-7">
          <Starfield className="absolute inset-0 h-full w-full" />
          <div className="absolute inset-0 bg-gradient-to-r from-[#05070c]/95 via-[#05070c]/60 to-[#05070c]/20" />
          <div className="relative grid h-full gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <div className="flex flex-col">
              <h1 className="display-caps text-4xl text-white sm:text-5xl">Star Vetter</h1>
              <p className="display-caps mt-3 text-xs leading-6 text-white/70 sm:text-sm">
                Autonomous vetting of
                <br />
                TESS eclipsing binaries
              </p>
              <p className="mt-5 max-w-md text-sm leading-relaxed text-white/75">
                An unattended agent that screens unexamined TESS targets for real eclipsing binary
                stars - statistical vetting, cross-matching against {stats?.catalogs.length ?? 6}{" "}
                catalogs and pixel-level confirmation - and writes every survivor up as a dossier.
                Every number on this site comes from the pipeline itself.
              </p>
              {stats?.catalog_progress && (
                <div className="mt-5 max-w-md">
                  <div className="flex items-baseline justify-between gap-3 text-xs text-white/70">
                    <span>
                      <span className="font-mono text-white">
                        {stats.catalog_progress.sampled_to_date.toLocaleString("en-US")}
                      </span>{" "}
                      of{" "}
                      <span className="font-mono text-white">
                        {stats.catalog_progress.total_catalog.toLocaleString("en-US")}
                      </span>{" "}
                      TESS targets screened
                    </span>
                    <span className="font-mono text-white/85">
                      {(stats.catalog_progress.fraction * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-white/70"
                      style={{
                        width: `${Math.max(0.4, Math.min(100, stats.catalog_progress.fraction * 100))}%`,
                      }}
                    />
                  </div>
                </div>
              )}
              <div className="mt-5 flex flex-wrap gap-3">
                <Link
                  href="/candidates"
                  className="inline-flex items-center gap-2 rounded-md bg-white px-4 py-2 text-sm font-medium text-[#05070c] hover:bg-white/90"
                >
                  View candidates <IconArrow className="h-4 w-4" />
                </Link>
                <Link
                  href="/about"
                  className="inline-flex items-center rounded-md border border-white/30 px-4 py-2 text-sm text-white hover:border-white/60"
                >
                  How it works
                </Link>
              </div>
              <WhatIsThis />
            </div>
            {dash && dash.sky.some((p) => p.ra !== null) && (
              <div className="relative self-center">
                <SkyMap points={dash.sky} highlight={featured.tic} className="w-full" />
                <div className="mt-2 inline-flex flex-col rounded-md border border-white/20 bg-black/55 px-3 py-2 text-[11px] text-white/85 backdrop-blur lg:absolute lg:right-0 lg:top-0 lg:mt-0">
                  <span className="font-mono text-sm text-white">TIC {featured.tic}</span>
                  <span className="font-mono">P = {P.toFixed(4)} d</span>
                  <span style={{ color: TIER_STYLE[featured.tier].chart }}>Strongest detection</span>
                </div>
              </div>
            )}
            {funnel.length > 0 && (
              <dl className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-3 lg:col-span-2 lg:grid-cols-6">
                {funnel.map((s) => (
                  <div key={s.label} className="border-l border-white/20 pl-3">
                    <dd className="font-mono text-2xl text-white">{s.count.toLocaleString("en-US")}</dd>
                    <dt className="mt-0.5 text-xs text-white/65">{SHORT[s.label] ?? s.label}</dt>
                    <dt className="font-mono text-[10px] text-white/40">
                      {total > 0 ? `${((100 * s.count) / total).toFixed(1)}%` : ""}
                    </dt>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </section>

        <div className="grid min-w-0 gap-4 xl:col-span-5">
          <Panel title="The pipeline" subtitle="From raw TESS data to a vetted, written-up candidate" href="/about" hrefLabel="Methods">
            <PipelineStages
              funnel={funnel}
              catalogs={stats?.catalogs ?? []}
              featured={featured}
              detail={featuredDetail}
              dossiers={meta ? meta.dossiers_available.length || null : null}
            />
          </Panel>
          {latest && (
            <Panel title="Latest run" subtitle={latest.log_file}>
              <LatestRun run={latest} funnel={funnel} runsLogged={dash?.runs.length ?? 0} />
            </Panel>
          )}
        </div>
      </div>

      <Explorer
        summaries={summaries}
        initialTic={featured.tic}
        initialDetail={featuredDetail}
        dossiers={meta?.dossiers_available ?? []}
        runsSlot={dash && dash.runs.length > 0 ? <RunsTable runs={dash.runs} /> : <NoData />}
        activitySlot={dash && dash.activity.length > 0 ? <ActivityFeed events={dash.activity} /> : <NoData />}
      />
    </main>
  );
}

function NoData() {
  return <p className="text-xs text-faint">Run export_dashboard.py to fill this in from the orchestrator logs.</p>;
}