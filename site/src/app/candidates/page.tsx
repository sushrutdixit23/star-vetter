import { Suspense, createElement } from "react";
import { getAllCandidates, getSiteMeta } from "@/lib/data";
import { toCardData } from "@/lib/cards";
import CandidateBrowser from "@/components/CandidateBrowser";

export const metadata = {
  title: "Candidates - Star Vetter",
};

export default function CandidatesPage() {
  const cards = getAllCandidates().map(toCardData);
  const meta = getSiteMeta();

  return (
    <main className="mx-auto w-full max-w-[1920px] flex-1 px-3 py-8 sm:px-6 sm:py-10">
      <p className="display-caps text-xs text-accent">Confirmed candidates</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-fg">
        {cards.length} eclipsing binaries, confirmed on-target
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
        Every star here passed statistical vetting, matched none of the
        cross-checked catalogs, and was confirmed at the pixel level. The tier
        badge carries any caveat the pipeline raised.
        {meta?.combined_dossier && (
          <>
            {" "}
            {createElement(
              "a",
              {
                href: meta.combined_dossier,
                className: "text-accent hover:underline",
                download: true,
              },
              "Download all dossiers (PDF)"
            )}
            .
          </>
        )}
      </p>

      <div className="mt-8">
        <Suspense fallback={null}>
          <CandidateBrowser cards={cards} />
        </Suspense>
      </div>
    </main>
  );
}
