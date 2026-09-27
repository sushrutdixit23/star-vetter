import { getDashboard } from "@/lib/data";
import SkyMap from "@/components/dash/SkyMap";
import { TIER_STYLE } from "@/lib/tiers";

export const metadata = {
  title: "Sky - Star Vetter",
};

// Standalone full-sky view of every confirmed candidate's real catalog
// position. All geometry (Mollweide projection, galactic plane) comes from
// lib/sky.ts via the existing SkyMap component - this page only adds the
// framing text, a legend matching the site's usual Clean/Period alias/
// Flagged grouping, and a count of what is actually plotted.
export default function SkyPage() {
  const dash = getDashboard();
  const points = (dash?.sky ?? []).filter((p) => p.ra !== null && p.dec !== null);

  return (
    <main className="mx-auto w-full max-w-[1400px] flex-1 space-y-6 px-3 py-8 sm:px-6 sm:py-10">
      <div>
        <div className="nav-caps text-xs text-accent">III. The sky</div>
        <h1 className="mt-1 font-display text-4xl italic text-fg sm:text-5xl">
          Where the survivors are.
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          Every confirmed candidate, plotted at its real catalog position on the whole sky. Right
          ascension increases to the left from 0h at the centre; the gold line traces the galactic
          plane.
        </p>
      </div>

      {points.length === 0 ? (
        <p className="text-xs text-faint">Run export_dashboard.py to add sky positions.</p>
      ) : (
        <div className="rounded-xl border border-line bg-panel p-4 sm:p-6">
          <SkyMap points={points} className="w-full" />
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: TIER_STYLE.CLEAN.chart }} />
              Clean
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: TIER_STYLE["PERIOD ALIAS"].chart }} />
              Period alias
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: TIER_STYLE["THIN MARGIN"].chart }} />
              Flagged
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4" style={{ background: "rgba(251,191,36,0.6)" }} />
              Galactic plane
            </span>
          </div>
          <p className="mt-3 text-[11px] text-faint">
            {points.length} confirmed candidate{points.length === 1 ? "" : "s"} shown, each at its
            real catalog RA/Dec. Hover a point for its TIC number.
          </p>
        </div>
      )}
    </main>
  );
}
