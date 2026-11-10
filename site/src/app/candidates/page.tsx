import { Suspense, createElement } from "react";
import { getAllCandidates, getDashboard, getGaiaContext, getNoveltyExtraMap, getSiteMeta } from "@/lib/data";
import { toCardData } from "@/lib/cards";
import CandidateBrowser from "@/components/CandidateBrowser";

export const metadata = {
  title: "Candidates - Star Vetter",
};

export default function CandidatesPage() {
  const gaia = getGaiaContext();
  const nov = getNoveltyExtraMap();
  const catName = (k: string) => ({ ztf: "ZTF", crts: "CRTS", wise: "WISE", atlas: "ATLAS", asas: "ASAS-3", kelt: "KELT" } as Record<string, string>)[k] ?? k;
  const cards = getAllCandidates().map((c) => {
    const n = nov?.[String(c.tic)];
    return {
      ...toCardData(c),
      ruweElevated: gaia ? gaia[String(c.tic)]?.elevated_ruwe ?? null : null,
      alreadyKnown: n?.verdict === "ALREADY_KNOWN" ? n.matched_catalogs.map(catName).join(", ") : null,
    };
  });
  const nKnown = cards.filter((c) => c.alreadyKnown).length;
  const meta = getSiteMeta();
  const skyPoints = getDashboard()?.sky ?? [];

  return (
    <main className="w-full flex-1 px-4 py-10 sm:px-8 xl:px-12">
      <div className="grid gap-6 border-b border-line pb-8 lg:grid-cols-[3rem_minmax(0,1fr)]">
        <div className="font-display text-3xl leading-none text-faint">II</div>
        <div>
          <div className="nav-caps font-mono text-[11px] text-muted">The survivors</div>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">{cards.length} candidates made it through <em>every test</em>.</h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">
            Each one passed statistical vetting and had its dimming centred on its own star at the pixel level. They are eclipsing-binary candidates, not published discoveries. Every star was also checked against six variable-star catalogs: {nKnown} turned out to be already listed at the same period (marked Already known and sorted last), and the rest show no match, which is weak evidence of novelty because those catalogs list only about 15% of known binaries. The tier badge carries any caveat the pipeline raised.
            {meta?.combined_dossier && (
              <>
                {" "}
                {createElement("a", { href: meta.combined_dossier, className: "text-accent hover:underline", download: true }, "Download all dossiers (PDF)")}
                .
              </>
            )}
          </p>
        </div>
      </div>

      <div className="mt-8">
        <Suspense fallback={null}>
          <CandidateBrowser cards={cards} skyPoints={skyPoints} />
        </Suspense>
      </div>
    </main>
  );
}
