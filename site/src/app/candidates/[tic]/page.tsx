import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import {
  getAllTics,
  getCandidate,
  getDetail,
  getIndex,
  getSiteMeta,
  getTimeseries,
  toSummary,
} from "@/lib/data";
import { TIER_STYLE } from "@/lib/tiers";
import TierBadge from "@/components/TierBadge";
import {
  AliasPanel,
  Card,
  CatalogPanel,
  CaveatsList,
  EclipseProfiles,
  LightCurvePanel,
  PixelEvidence,
  QuickActions,
  StatsTable,
  TimingPanel,
} from "@/components/dash/DetailPanels";
import { summaryLine } from "@/lib/summary";
import OrbitSchematic from "@/components/plate/OrbitSchematic";
import NextEclipses from "@/components/plate/NextEclipses";
import FoldItYourself from "@/components/plate/FoldItYourself";

// The permalink target every "Share", card, and search result on the site
// points a TIC number at. Laid out as a "specimen plate": one narrative
// pass through the evidence (I-V), then every raw number and chart this
// page used to show inline is still here, collapsed into "Instrument" at
// the bottom - nothing that worked before was removed, only reordered
// around a story a first-time visitor can actually follow.

export async function generateStaticParams() {
  return getAllTics().map((tic) => ({ tic: String(tic) }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ tic: string }>;
}) {
  const { tic: ticParam } = await params;
  return { title: `TIC ${ticParam} - Star Vetter` };
}

function Section({
  num,
  title,
  lede,
  aside,
  children,
}: {
  num: string;
  title: string;
  lede?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-xl border border-line bg-panel p-4 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-2xl italic text-faint">{num}</span>
          <h2 className="nav-caps text-sm text-fg">{title}</h2>
        </div>
        {aside && <div className="text-[11px] text-muted">{aside}</div>}
      </div>
      {lede && <p className="mt-2 max-w-2xl text-sm text-muted">{lede}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default async function CandidatePage({
  params,
}: {
  params: Promise<{ tic: string }>;
}) {
  const { tic: ticParam } = await params;
  const tic = Number(ticParam);
  const allTics = getAllTics();
  if (!allTics.includes(tic)) {
    notFound();
  }

  const c = getCandidate(tic);
  const s = toSummary(c);
  const d = getDetail(tic);
  const ts = getTimeseries(tic);
  const meta = getSiteMeta();
  const hasDossier = meta ? meta.dossiers_available.includes(tic) : false;
  const color = TIER_STYLE[s.tier].chart;

  const ordered = [...getIndex().candidates].sort((a, b) => b.bls_snr - a.bls_snr);
  const pos = ordered.findIndex((r) => r.tic === tic);
  const prevTic = pos > 0 ? ordered[pos - 1].tic : null;
  const nextTic = pos >= 0 && pos < ordered.length - 1 ? ordered[pos + 1].tic : null;

  const hasCaveats = (d?.checks.length ?? 0) > 0 || s.caveats.some((cv) => cv.tier !== "CLEAN");

  return (
    <main className="mx-auto w-full max-w-[1400px] flex-1 space-y-4 px-3 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <Link href="/candidates" className="nav-caps text-xs text-muted hover:text-fg">
            &larr; all candidates
          </Link>
          <Link href={`/?tic=${tic}`} className="nav-caps text-xs text-accent/80 hover:text-accent">
            open in interactive explorer &rarr;
          </Link>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {prevTic ? (
            <Link href={`/candidates/${prevTic}`} className="nav-caps text-muted hover:text-fg">
              &larr; prev
            </Link>
          ) : (
            <span className="nav-caps text-faint">&larr; prev</span>
          )}
          <span className="font-mono text-faint">
            {pos + 1} / {ordered.length}
          </span>
          {nextTic ? (
            <Link href={`/candidates/${nextTic}`} className="nav-caps text-muted hover:text-fg">
              next &rarr;
            </Link>
          ) : (
            <span className="nav-caps text-faint">next &rarr;</span>
          )}
        </div>
      </div>

      {/* ---------- plate header ---------- */}
      <section className="min-w-0 rounded-xl border border-line bg-panel p-4 sm:p-6">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div>
            <div className="nav-caps text-xs text-faint">Candidate</div>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <h1 className="font-mono text-3xl text-fg sm:text-4xl">TIC {s.tic}</h1>
              <TierBadge tier={s.tier} />
            </div>
            <p className="mt-2 max-w-xl text-sm text-muted">{summaryLine(s, d)}</p>
            <div className="mt-4 max-w-md">
              <OrbitSchematic tier={s.tier} className="h-24 w-full text-fg" />
              <p className="mt-1 text-[10px] text-faint">
                Schematic diagram - not to scale, and not a measurement of either star&apos;s true
                size or colour.
              </p>
            </div>
          </div>
          <NextEclipses d={d} />
        </div>
      </section>

      {/* ---------- I. the signal ---------- */}
      <Section num="I" title="The signal" lede="A repeating, consistent dip in brightness.">
        <LightCurvePanel s={s} d={d} />
        <div className="mt-4">
          <div className="mb-2 text-xs text-muted">Close-up of each eclipse</div>
          <EclipseProfiles s={s} d={d} />
        </div>
      </Section>

      {/* ---------- II. the catalog check ---------- */}
      <Section
        num="II"
        title="The catalog check"
        lede="Cross-matched against known variable-star catalogs to rule out anything already listed."
      >
        <CatalogPanel s={s} />
      </Section>

      {/* ---------- III. the pixel check ---------- */}
      <Section
        num="III"
        title="The pixel check"
        lede="Confirms the dimming is on the target star, not a nearby source."
        aside={`TESS sector ${s.pixel.sector}`}
      >
        <PixelEvidence s={s} d={d} />
      </Section>

      {/* ---------- IV. fold it yourself ---------- */}
      <Section num="IV" title="Fold it yourself" lede="Adjust the period and see the eclipse appear.">
        <FoldItYourself d={d} ts={ts} color={color} />
      </Section>

      {/* ---------- V. caveats ---------- */}
      <Section num="V" title="Caveats" lede="Known limitations and things to check.">
        {hasCaveats ? (
          <div className="space-y-1.5">
            {(d?.checks ?? []).map((chk, i) => (
              <p
                key={`chk-${i}`}
                className="rounded-md border border-rose-400/40 bg-rose-400/10 px-2.5 py-1.5 text-[11px] leading-snug text-fg/90"
              >
                <span className="mr-1 font-medium text-rose-300">Cross-check:</span>
                {chk}
              </p>
            ))}
            <CaveatsList caveats={s.caveats} />
          </div>
        ) : (
          <p className="text-sm text-muted">
            No caveats flagged. This candidate cleared every gate with no named exception - see
            Instrument below for the raw numbers.
          </p>
        )}
      </Section>

      {/* ---------- instrument (raw values, collapsed) ---------- */}
      <details className="group rounded-xl border border-line bg-panel p-4 sm:p-6">
        <summary className="nav-caps cursor-pointer text-sm text-fg marker:text-faint">
          Instrument - raw values, fits and technical details
        </summary>
        <div className="mt-4 space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Full statistics">
              <StatsTable s={s} d={d} />
            </Card>
            <Card title="Period alias analysis">
              <AliasPanel s={s} d={d} />
            </Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="O - C timing" aside="primary eclipses">
              <TimingPanel d={d} />
            </Card>
            <Card title="Quick actions">
              <QuickActions s={s} d={d} hasDossier={hasDossier} />
            </Card>
          </div>
        </div>
      </details>
    </main>
  );
}
