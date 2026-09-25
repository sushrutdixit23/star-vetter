import Link from "next/link";
import { notFound } from "next/navigation";
import { getAllTics, getCandidate, getDetail, getSiteMeta, toSummary } from "@/lib/data";
import {
  AliasPanel,
  Card,
  CatalogPanel,
  DetailHeader,
  EclipseProfiles,
  LightCurvePanel,
  PixelEvidence,
  QuickActions,
  StatsTable,
  TimingPanel,
} from "@/components/dash/DetailPanels";

// This is the permalink target every "Share", card, and search result on
// the site points a TIC number at - so it renders the exact same panels as
// the home page's interactive explorer (via the shared toSummary() mapping
// in lib/data.ts), just for one star with no picker sidebar. It used to be
// a separate, older, plainer page; keeping the two in sync means a shared
// link never lands somewhere less complete than where it was shared from.

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
  const meta = getSiteMeta();
  const hasDossier = meta ? meta.dossiers_available.includes(tic) : false;

  return (
    <main className="mx-auto w-full max-w-[1400px] flex-1 space-y-4 px-3 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-center gap-4">
        <Link href="/candidates" className="font-mono text-xs uppercase tracking-wide text-muted hover:text-fg">
          &larr; all candidates
        </Link>
        <Link href={`/?tic=${tic}`} className="font-mono text-xs uppercase tracking-wide text-accent/80 hover:text-accent">
          open in interactive explorer &rarr;
        </Link>
      </div>

      <section className="min-w-0 rounded-xl border border-line bg-panel p-4 sm:p-6">
        <DetailHeader s={s} d={d} hasDossier={hasDossier} />
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <StatsTable s={s} d={d} />
          <EclipseProfiles s={s} d={d} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Light curve" aside="phase folded at the true period">
          <LightCurvePanel s={s} d={d} />
        </Card>
        <Card title="Period alias analysis">
          <AliasPanel s={s} d={d} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Pixel evidence" aside={`TESS sector ${s.pixel.sector}`}>
          <PixelEvidence s={s} d={d} />
        </Card>
        <Card title="O - C timing" aside="primary eclipses">
          <TimingPanel d={d} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <Card title="Catalog cross-match" aside={`TIC ${s.tic}`}>
          <CatalogPanel s={s} />
        </Card>
        <Card title="Quick actions">
          <QuickActions s={s} d={d} hasDossier={hasDossier} />
        </Card>
      </div>
    </main>
  );
}
