import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { getAllCandidates, getAllTics, getCandidate, getDetail, getGaiaContext, getGroundSurvey, getSiteMeta, getTimeseries, toSummary } from "@/lib/data";
import { bestPeriod } from "@/lib/cards";
import { TIER_STYLE } from "@/lib/tiers";
import { summaryLine } from "@/lib/summary";
import { safeWriteup } from "@/lib/writeup";
import TierBadge from "@/components/TierBadge";
import { AliasPanel, Card, CatalogPanel, CaveatsList, EclipseProfiles, LightCurvePanel, PixelEvidence, QuickActions, StatsTable, TimingPanel } from "@/components/dash/DetailPanels";
import OrbitSchematic from "@/components/plate/OrbitSchematic";
import NextEclipses from "@/components/plate/NextEclipses";
import FoldItYourself from "@/components/plate/FoldItYourself";
import CandidateSidebar, { type SidebarItem } from "@/components/plate/CandidateSidebar";
import GaiaContextPanel, { gaiaVerdict } from "@/components/plate/GaiaContextPanel";
import GroundSurveyPanel, { groundSurveyVerdict } from "@/components/plate/GroundSurveyPanel";

// The specimen plate: the permalink every card, search result and share
// link points at. A sidebar of every survivor, a header, then five
// evidence rows (text | evidence | verdict), with every raw number and
// chart this page has ever shown kept in the Instrument drawer at the end.

export async function generateStaticParams() {
  return getAllTics().map((tic) => ({ tic: String(tic) }));
}

export async function generateMetadata({ params }: { params: Promise<{ tic: string }> }) {
  const { tic: ticParam } = await params;
  return { title: `TIC ${ticParam} - Star Vetter` };
}

// Built once per build worker, not once per page: every plate shares the
// same list, so re-reading all candidate files for each page is wasted work.
let SIDEBAR: SidebarItem[] | null = null;
function sidebarItems(): SidebarItem[] {
  if (SIDEBAR) return SIDEBAR;
  SIDEBAR = getAllCandidates()
    .map((c) => {
      const b = c.light_curve.binned;
      const step = Math.max(1, Math.ceil(b.length / 48));
      return { tic: c.tic, tier: c.tier, period: bestPeriod(c), depth: c.ephemeris.depth_frac, snr: c.ephemeris.bls_snr, binned: b.filter((_, i) => i % step === 0) };
    })
    .sort((a, b) => b.snr - a.snr);
  return SIDEBAR;
}

// A finer fold than the export's 144 bins, built from the raw points, so a
// narrow eclipse keeps its real shape and depth in the orbit's mini curve.
function fineCurve(raw: [number, number][]): [number, number][] {
  const BINS = 360;
  const buckets: number[][] = Array.from({ length: BINS }, () => []);
  for (const [ph, fx] of raw) {
    if (!Number.isFinite(ph) || !Number.isFinite(fx)) continue;
    let i = Math.floor((ph + 0.5) * BINS);
    if (i < 0) i = 0;
    if (i >= BINS) i = BINS - 1;
    buckets[i].push(fx);
  }
  const out: [number, number][] = [];
  buckets.forEach((b, i) => {
    if (b.length === 0) return;
    const sorted = [...b].sort((x, y) => x - y);
    const median = sorted[Math.floor(sorted.length / 2)];
    out.push([Math.round(((i + 0.5) / BINS - 0.5) * 10000) / 10000, Math.round(median * 100000) / 100000]);
  });
  return out;
}

function roman(n: number): string {
  const map: [number, string][] = [[100, "C"], [90, "XC"], [50, "L"], [40, "XL"], [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let v = n;
  let out = "";
  for (const [k, sym] of map) {
    while (v >= k) {
      out += sym;
      v -= k;
    }
  }
  return out;
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true">
      <path d="M3 8.5 L6.5 12 L13 4.5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

interface VerdictProps {
  kind: "pass" | "warn";
  label: string;
  note?: string;
  rows?: [string, string][];
}

function Verdict({ kind, label, note, rows }: VerdictProps) {
  const pass = kind === "pass";
  return (
    <div className="rounded-lg border border-line bg-panel/60 p-4">
      <div className="flex items-start gap-3">
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${pass ? "bg-accent/20 text-accent" : "bg-accent-cool/20 text-accent-cool"}`}>
          {pass ? <CheckIcon /> : <span className="font-mono text-sm font-bold">!</span>}
        </span>
        <div>
          <div className={`nav-caps font-mono text-xs ${pass ? "text-accent" : "text-accent-cool"}`}>{label}</div>
          {note && <p className="mt-1 text-[12px] leading-snug text-muted">{note}</p>}
        </div>
      </div>
      {rows && rows.length > 0 && (
        <dl className="mt-4 space-y-1.5 font-mono text-[11px]">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 border-b border-line pb-1">
              <dt className="text-faint">{k}</dt>
              <dd className="text-right text-fg">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function Row({ num, title, lede, verdict, children }: { num: string; title: string; lede?: string; verdict?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-line py-8">
      <div className="grid gap-6 lg:grid-cols-[2.5rem_minmax(0,12rem)_minmax(0,1fr)] 2xl:grid-cols-[2.5rem_minmax(0,12rem)_minmax(0,1fr)_16rem]">
        <div className="font-display text-3xl leading-none text-faint">{num}</div>
        <div>
          <h2 className="font-display text-lg uppercase tracking-[0.16em] text-fg">{title}</h2>
          {lede && <p className="mt-2 text-sm leading-relaxed text-muted">{lede}</p>}
        </div>
        <div className="min-w-0">{children}</div>
        {verdict ? <div className="lg:col-start-3 2xl:col-start-auto">{verdict}</div> : <div className="hidden 2xl:block" />}
      </div>
    </section>
  );
}

export default async function CandidatePage({ params }: { params: Promise<{ tic: string }> }) {
  const { tic: ticParam } = await params;
  const tic = Number(ticParam);
  if (!getAllTics().includes(tic)) {
    notFound();
  }

  const c = getCandidate(tic);
  const s = toSummary(c);
  const d = getDetail(tic);
  const ts = getTimeseries(tic);
  const meta = getSiteMeta();
  const hasDossier = meta ? meta.dossiers_available.includes(tic) : false;
  const color = TIER_STYLE[s.tier].chart;
  const orbitCurve = d ? fineCurve(d.fold.raw) : null;
  const gaiaAll = getGaiaContext();
  const gaia = gaiaAll ? gaiaAll[String(tic)] ?? null : null;
  const gaiaV = gaiaVerdict(gaia);
  const groundSurveyAll = getGroundSurvey();
  const groundSurvey = groundSurveyAll ? groundSurveyAll[String(tic)] ?? null : null;
  const groundSurveyV = groundSurveyVerdict(groundSurvey);
  const writeup = safeWriteup(d?.writeup, tic);

  const items = sidebarItems();
  const pos = items.findIndex((r) => r.tic === tic);
  const prevTic = pos > 0 ? items[pos - 1].tic : null;
  const nextTic = pos >= 0 && pos < items.length - 1 ? items[pos + 1].tic : null;

  const period = d ? d.period_true_days : s.corrected_period_days ?? s.period_days;
  const primaryDepth = d?.primary?.depth ?? s.depth_frac;
  const checks = d?.checks ?? [];
  const hasCaveats = checks.length > 0 || s.caveats.some((cv) => cv.tier !== "CLEAN");
  const matched = s.catalogs.filter((x) => x.matched).length;
  const flaggedPixel = s.tier === "THIN MARGIN" || s.tier === "MARGINAL" || s.tier === "AMBIGUOUS PHOTOMETRY";

  const signalRows: [string, string][] = [
    ["Period", `${period.toFixed(5)} d`],
    ["Primary depth", `${(primaryDepth * 100).toFixed(2)}%`],
  ];
  if (d?.secondary?.detected) signalRows.push(["Secondary depth", `${(d.secondary.depth * 100).toFixed(2)}%`]);
  if (d) signalRows.push(["Epoch (T0)", `${d.t0_btjd.toFixed(3)} BTJD`]);
  signalRows.push(["Duration", `${(s.duration_days * 24).toFixed(2)} h`]);

  const signalVerdict: VerdictProps = checks.length > 0
    ? { kind: "warn", label: "Flagged", note: "Automated cross-checks question this period - see Caveats below.", rows: signalRows }
    : s.aliased
      ? { kind: "warn", label: "Period alias", note: "Alternate eclipses differ in depth, so the true period is twice the search period.", rows: signalRows }
      : { kind: "pass", label: "Pass", note: "Clear, repeating eclipses with a consistent period and depth.", rows: signalRows };

  const pixelRows: [string, string][] = [
    ["Centroid offset", `${s.pixel.centroid_offset_px.toFixed(2)} px`],
    ["Difference SNR", s.pixel.diff_peak_snr.toFixed(1)],
    ["Capable neighbour", s.pixel.nearest ? `TIC ${s.pixel.nearest.tic}` : "none"],
    ["TESS sector", String(s.pixel.sector)],
  ];

  const foldRows: [string, string][] = [
    ["True period", `${period.toFixed(5)} d`],
    ["BLS period", `${s.period_days.toFixed(5)} d`],
    ["Odd/even z", s.odd_even_z === null ? "-" : s.odd_even_z.toFixed(2)],
  ];

  return (
    <main className="w-full flex-1">
      <div className="lg:grid lg:grid-cols-[19rem_minmax(0,1fr)]">
        <aside className="hidden border-r border-line lg:block">
          <div className="sticky top-[3.75rem] h-[calc(100vh-3.75rem)]">
            <CandidateSidebar items={items} current={tic} />
          </div>
        </aside>

        <div className="min-w-0 px-4 py-6 sm:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4 font-mono text-[11px]">
            <div className="flex items-center gap-3">
              {pos >= 0 && <span className="nav-caps rounded border border-line px-2 py-0.5 text-muted">Plate {roman(pos + 1)}</span>}
              <Link href="/candidates" className="nav-caps text-muted hover:text-fg lg:hidden">&larr; All candidates</Link>
            </div>
            <div className="flex items-center gap-4">
              {prevTic ? <Link href={`/candidates/${prevTic}`} className="nav-caps text-muted hover:text-fg">&larr; Prev</Link> : <span className="nav-caps text-faint">&larr; Prev</span>}
              <span className="text-faint">{pos + 1} / {items.length}</span>
              {nextTic ? <Link href={`/candidates/${nextTic}`} className="nav-caps text-muted hover:text-fg">Next &rarr;</Link> : <span className="nav-caps text-faint">Next &rarr;</span>}
            </div>
          </div>

          <section className="grid gap-8 py-8 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_17rem]">
            <div>
              <div className="nav-caps font-mono text-[11px] text-muted">Candidate</div>
              <h1 className="mt-2 font-display text-5xl leading-none text-fg sm:text-6xl">TIC {s.tic}</h1>
              <p className="mt-3 font-display text-lg text-muted">An uncatalogued eclipsing-binary candidate from TESS.</p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <TierBadge tier={s.tier} />
                <span className="nav-caps rounded-full border border-line px-2.5 py-0.5 font-mono text-[10px] text-fg">Survivor</span>
                <span className="rounded-full border border-line px-2.5 py-0.5 font-mono text-[11px] text-accent">P = {period.toFixed(5)} d</span>
              </div>
              <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted">{summaryLine(s, d)}</p>
              {writeup && (
                <div className="mt-5 max-w-xl border-l-2 border-accent/40 pl-4">
                  <div className="nav-caps font-mono text-[10px] text-faint">In plain English</div>
                  <p className="mt-1 text-sm leading-relaxed text-fg/90">{writeup}</p>
                </div>
              )}
            </div>
            <div className="flex flex-col justify-center">
              <OrbitSchematic teff={d?.catalog.teff_k ?? null} period={period} t0={d ? d.t0_btjd : c.ephemeris.t0_btjd} depth1={d?.primary ? d.primary.depth : null} depth2={d?.secondary && d.secondary.detected ? d.secondary.depth : null} secPhase={d?.secondary && d.secondary.detected ? d.secondary.phase : null} duration={d ? d.duration_days : s.duration_days} depth2Upper={d?.secondary && !d.secondary.detected ? Math.max(d.secondary.depth, 0) + 5 * d.secondary.err : null} curve={orbitCurve} sinusoid={Boolean(d?.periodicity?.flag)} className="w-full text-fg" />
            </div>
            <NextEclipses d={d} />
          </section>

          <Row num="I" title="The signal" lede="A repeating, consistent dip in brightness." verdict={<Verdict {...signalVerdict} />}>
            <LightCurvePanel s={s} d={d} />
          </Row>

          <Row num="II" title="The catalog check" lede="Cross-matched against known variable-star catalogs to rule out anything already listed." verdict={<Verdict kind={matched === 0 ? "pass" : "warn"} label={matched === 0 ? "Pass" : "Matched"} note={matched === 0 ? "No known variable star or catalogued match at this position." : "A catalog lists a known variable at this position."} rows={[["Catalogs checked", String(s.catalogs.length)], ["Matches", String(matched)]]} />}>
            <CatalogPanel s={s} />
          </Row>

          <Row num="III" title="The pixel check" lede="Confirms the dimming is on the target star, not a nearby source." verdict={<Verdict kind={flaggedPixel ? "warn" : "pass"} label={flaggedPixel ? TIER_STYLE[s.tier].label : "Pass"} note={flaggedPixel ? TIER_STYLE[s.tier].blurb : "The dimming is centred on the target star. No nearby contaminant detected."} rows={pixelRows} />}>
            <PixelEvidence s={s} d={d} />
          </Row>

          <Row num="IV" title="The Gaia view" lede="A second spacecraft's measurements: how far away the star is, how bright and what colour, and whether its position fits a single star." verdict={gaiaV ? <Verdict {...gaiaV} /> : undefined}>
            <GaiaContextPanel gaia={gaia} all={gaiaAll} tic={tic} />
          </Row>

          <Row num="V" title="The ground-survey check" lede="An independent instrument, different years: does real ZTF photometry show the eclipse at the period TESS measured?" verdict={groundSurveyV ? <Verdict {...groundSurveyV} /> : undefined}>
            <GroundSurveyPanel g={groundSurvey} />
          </Row>

          <Row num="VI" title="Fold it yourself" lede="Adjust the period and watch the eclipse appear." verdict={<Verdict kind="pass" label="Best fit" note="The period the pipeline measured. Drag the slider away from it and the eclipse smears out." rows={foldRows} />}>
            <FoldItYourself d={d} ts={ts} color={color} />
          </Row>

          <Row num="VII" title="Caveats" lede="Known limitations and things to check.">
            {hasCaveats ? (
              <div className="space-y-1.5">
                {checks.map((chk, i) => (
                  <p key={`chk-${i}`} className="rounded-md border border-rose-400/40 bg-rose-400/10 px-2.5 py-1.5 text-[11px] leading-snug text-fg/90">
                    <span className="mr-1 font-medium text-rose-300">Cross-check:</span>
                    {chk}
                  </p>
                ))}
                <CaveatsList caveats={s.caveats} />
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-4">
                <span className="nav-caps rounded-full border border-emerald-400/40 bg-emerald-400/10 px-3 py-1 font-mono text-[10px] text-emerald-300">None found</span>
                <p className="max-w-xl text-sm text-muted">No caveats flagged: this candidate cleared every gate with no named exception. Follow-up observations would still be needed to confirm the stellar parameters.</p>
              </div>
            )}
          </Row>

          <details className="group border-t border-line py-8">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 [&::-webkit-details-marker]:hidden">
              <div className="flex items-baseline gap-6">
                <span className="w-10 font-display text-3xl leading-none text-faint">VIII</span>
                <div>
                  <h2 className="font-display text-lg uppercase tracking-[0.16em] text-fg">Instrument</h2>
                  <p className="mt-1 text-sm text-muted">Raw values, fits and technical details.</p>
                </div>
              </div>
              <span className="nav-caps shrink-0 rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg group-open:border-accent/60">
                <span className="group-open:hidden">Show raw data</span>
                <span className="hidden group-open:inline">Hide raw data</span>
              </span>
            </summary>
            <div className="mt-6 space-y-4">
              <div className="grid gap-4 xl:grid-cols-2">
                <Card title="Full statistics">
                  <StatsTable s={s} d={d} />
                </Card>
                <Card title="Eclipse close-ups">
                  <EclipseProfiles s={s} d={d} />
                </Card>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <Card title="Period alias analysis">
                  <AliasPanel s={s} d={d} />
                </Card>
                <Card title="O - C timing" aside="primary eclipses">
                  <TimingPanel d={d} />
                </Card>
              </div>
              <Card title="Quick actions">
                <QuickActions s={s} d={d} hasDossier={hasDossier} />
              </Card>
            </div>
          </details>
        </div>
      </div>
    </main>
  );
}
