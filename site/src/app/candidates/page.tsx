import { Suspense, createElement } from "react";
import { getAllCandidates, getDashboard, getSiteMeta } from "@/lib/data";
import { toCardData } from "@/lib/cards";
import CandidateBrowser from "@/components/CandidateBrowser";

export const metadata = {
  title: "Candidates - Star Vetter",
};

export default function CandidatesPage() {
  const cards = getAllCandidates().map(toCardData);
  const meta = getSiteMeta();
  const skyPoints = getDashboard()?.sky ?? [];

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-10 sm:px-8">
      <div className="grid gap-6 border-b border-line pb-8 lg:grid-cols-[3rem_minmax(0,1fr)]">
        <div className="font-display text-3xl leading-none text-faint">II</div>
        <div>
          <div className="nav-caps font-mono text-[11px] text-muted">The survivors</div>
          <h1 className="mt-3 font-display text-4xl leading-[1.05] text-fg sm:text-5xl">{cards.length} candidates made it through <em>every test</em>.</h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">
            Each one passed statistical vetting, matched none of the cross-checked catalogs, and had its dimming centred on its own star at the pixel level. They are uncatalogued eclipsing-binary candidates, not published discoveries; the tier badge carries any caveat the pipeline raised.
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
