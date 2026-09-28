import Link from "next/link";
import { getAllCandidates, getDashboard, getDetail, getPipelineStats, getSiteMeta } from "@/lib/data";
import Panel from "@/components/Panel";
import PipelineStages from "@/components/dash/PipelineStages";
import SkyMap from "@/components/dash/SkyMap";
import { ActivityFeed, LatestRun, RunsTable } from "@/components/dash/RunPanels";
import { IconArrow } from "@/components/icons";
import WhatIsThis from "@/components/WhatIsThis";
import Band from "@/components/journal/Band";
import HeroGauntlet from "@/components/journal/HeroGauntlet";
import EclipseExplainer from "@/components/journal/EclipseExplainer";
import NeighbourTest from "@/components/journal/NeighbourTest";
import SurvivorClocks from "@/components/journal/SurvivorClocks";
import TicRedirect from "@/components/journal/TicRedirect";

// The journal: seven sections in the order of the story - the machine,
// its gauntlet, what an eclipse is, the impostor test, the survivors,
// where they are, and the machine still running. Every number comes from
// the pipeline's own exports in public/data.

const SHORT: Record<string, string> = {
  "Targets sampled and fetch attempted": "targets sampled",
  "Usable light curve obtained": "usable light curves",
  "Passed statistical vetting gates": "statistically passing",
  "Flagged novel (no catalog match)": "novel (catalog-unique)",
  "Survived contamination check, pixel-checked": "pixel-checked",
  "Confirmed on-target": "confirmed on-target",
};

const fmt = (n: number | undefined) => (n === undefined ? "-" : n.toLocaleString("en-US"));

export default function Home() {
  const stats = getPipelineStats();
  const meta = getSiteMeta();
  const dash = getDashboard();
  const candidates = getAllCandidates().sort((a, b) => b.ephemeris.bls_snr - a.ephemeris.bls_snr);
  const featured = candidates[0];
  const featuredDetail = getDetail(featured.tic);
  const funnel = stats?.funnel ?? [];
  const latest = dash?.runs[0] ?? null;

  const thin = (pts: [number, number][]) => {
    const step = Math.max(1, Math.ceil(pts.length / 90));
    return pts.filter((_, i) => i % step === 0);
  };
  const survivors = candidates.map((c) => {
    const d = c.tic === featured.tic ? featuredDetail : getDetail(c.tic);
    const fallback = c.light_curve.binned.filter((p): p is [number, number] => p[1] !== null);
    return {
      tic: c.tic,
      tier: c.tier,
      binned: thin(d ? d.fold.binned : fallback),
      period: d ? d.period_true_days : c.ephemeris.corrected_period_days ?? c.ephemeris.period_days,
      t0: d ? d.t0_btjd : c.ephemeris.t0_btjd,
      duration: d ? d.duration_days : c.ephemeris.duration_days,
      secondaryPhase: d && d.secondary && d.secondary.detected ? d.secondary.phase : null,
    };
  });

  const intro = (
    <>
      <div className="nav-caps font-mono text-[11px] text-muted">An autonomous observatory</div>
      <h1 className="mt-4 font-display text-4xl leading-[1.05] text-fg sm:text-5xl 2xl:text-6xl">I built a machine that hunts for new binary stars, then tries to <em>kill everything</em> it finds.</h1>
      <p className="mt-5 max-w-md text-sm leading-relaxed text-muted">An unattended agent that screens unexamined stars from NASA&apos;s TESS telescope for eclipsing binaries - statistical vetting, cross-matching against {stats?.catalogs.length ?? 6} catalogs, and pixel-level source confirmation. Every number on this site comes from the pipeline itself.</p>
      {stats?.catalog_progress && (
        <p className="mt-4 font-mono text-[11px] text-faint">{stats.catalog_progress.sampled_to_date.toLocaleString("en-US")} of {stats.catalog_progress.total_catalog.toLocaleString("en-US")} TESS targets examined ({(stats.catalog_progress.fraction * 100).toFixed(2)}%)</p>
      )}
      <div className="mt-7 flex flex-wrap gap-3">
        <Link href="/candidates" className="nav-caps inline-flex items-center gap-2 rounded-md bg-fg px-4 py-2.5 font-mono text-[11px] text-canvas hover:bg-fg/90">Explore candidates <IconArrow className="h-3.5 w-3.5" /></Link>
        <a href="#latest-run" className="nav-caps inline-flex items-center rounded-md border border-line px-4 py-2.5 font-mono text-[11px] text-fg hover:border-accent/60">View latest run</a>
      </div>
      <WhatIsThis />
    </>
  );

  return (
    <main className="w-full flex-1 px-4 sm:px-8 xl:px-12">
      <TicRedirect />

      <HeroGauntlet funnel={funnel} short={SHORT} intro={intro} />

      <div className="grid gap-12 border-t border-line py-10 2xl:grid-cols-2 2xl:gap-0">
        <div className="min-w-0 2xl:pr-10">
          <EclipseExplainer />
        </div>
        {featuredDetail?.pixel_maps && (
          <div className="min-w-0 2xl:border-l 2xl:border-line 2xl:pl-10">
            <NeighbourTest tic={featured.tic} maps={featuredDetail.pixel_maps} offsetPx={featured.pixel_check.centroid_offset_px} offsetArcsec={featured.pixel_check.centroid_offset_arcsec} nearest={featured.pixel_check.nearest_neighbour} failed={Math.max((funnel[4]?.count ?? 0) - (funnel[5]?.count ?? 0), 0)} reached={funnel[4]?.count ?? 0} />
          </div>
        )}
      </div>

      <SurvivorClocks survivors={survivors} />

      <div className="grid gap-12 border-t border-line py-10 2xl:grid-cols-2 2xl:gap-0">
        {dash && dash.sky.some((p) => p.ra !== null) && (
          <div className="min-w-0 2xl:pr-10">
            <Band variant="half" num="VI" title="The sky" lede="Every survivor at its real catalog position on the whole sky. Hover a point for its coordinates; click it to open the full evidence." action={<Link href="/sky" className="nav-caps inline-flex items-center rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg hover:border-accent/60">Full sky view &rarr;</Link>}>
              <SkyMap points={dash.sky} className="w-full" />
            </Band>
          </div>
        )}
        <div id="latest-run" className="min-w-0 scroll-mt-24 2xl:border-l 2xl:border-line 2xl:pl-10">
          <Band variant="half" num="VII" title="The machine is still running" lede="The pipeline keeps drawing and vetting new TESS targets on a schedule. Every number on this site comes from its latest completed run.">
            <div className="rounded-lg border border-line bg-panel/60 p-5">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                <span className="nav-caps font-mono text-[11px] text-fg">Latest run</span>
              </div>
              <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-8 gap-y-2 font-mono text-xs">
                <dt className="text-faint">Run ID</dt>
                <dd className="text-fg">{latest ? latest.id : "-"}</dd>
                <dt className="text-faint">Status</dt>
                <dd className="text-fg">{latest ? latest.status : "-"}</dd>
                <dt className="text-faint">Runtime</dt>
                <dd className="text-fg">{latest && latest.runtime_min !== null ? `${latest.runtime_min.toFixed(1)} min` : "-"}</dd>
                <dt className="text-faint">Examined to date</dt>
                <dd className="text-fg">{fmt(funnel[0]?.count)}</dd>
                <dt className="text-faint">Survived to date</dt>
                <dd className="text-fg">{fmt(funnel[5]?.count)}</dd>
              </dl>
              <a href="#run-details" className="nav-caps mt-5 inline-flex items-center rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg hover:border-accent/60">View run details &darr;</a>
            </div>
          </Band>
        </div>
      </div>

      <details id="run-details" className="scroll-mt-24 border-t border-line py-8">
        <summary className="nav-caps cursor-pointer font-mono text-[11px] text-muted marker:text-faint hover:text-fg">Run details - pipeline stages, activity and run history</summary>
        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <Panel title="The pipeline" subtitle="From raw TESS data to a vetted, written-up candidate" href="/about" hrefLabel="Methods">
              <PipelineStages funnel={funnel} catalogs={stats?.catalogs ?? []} featured={featured} detail={featuredDetail} dossiers={meta ? meta.dossiers_available.length || null : null} />
            </Panel>
          </div>
          <div className="xl:col-span-5">
            {latest && (
              <Panel title="Latest run" subtitle={latest.log_file}>
                <LatestRun run={latest} funnel={funnel} runsLogged={dash?.runs.length ?? 0} />
              </Panel>
            )}
          </div>
          <div className="xl:col-span-7">
            <Panel title="Latest run activity" subtitle="Orchestrator decisions, as logged">
              {dash && dash.activity.length > 0 ? <ActivityFeed events={dash.activity} /> : <NoData />}
            </Panel>
          </div>
          <div className="xl:col-span-5">
            <Panel title="Runs" subtitle="From the orchestrator logs">
              {dash && dash.runs.length > 0 ? <RunsTable runs={dash.runs} /> : <NoData />}
            </Panel>
          </div>
        </div>
      </details>
    </main>
  );
}

function NoData() {
  return <p className="text-xs text-faint">Run export_dashboard.py to fill this in from the orchestrator logs.</p>;
}
