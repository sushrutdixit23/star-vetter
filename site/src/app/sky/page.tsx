import { getDashboard } from "@/lib/data";
import SkyMap from "@/components/dash/SkyMap";

export const metadata = {
  title: "Sky - Star Vetter",
};

// Standalone full-sky view of every confirmed candidate's real catalog
// position. Geometry, legend and interaction all live in SkyMap, so this
// page and the Sky tab on /candidates stay identical.
export default function SkyPage() {
  const dash = getDashboard();
  const points = (dash?.sky ?? []).filter((p) => p.ra !== null && p.dec !== null);

  return (
    <main className="w-full flex-1 space-y-6 px-4 py-10 sm:px-8 xl:px-12">
      <div>
        <div className="nav-caps text-xs text-accent">The sky</div>
        <h1 className="mt-1 font-display text-4xl italic text-fg sm:text-5xl">Where the survivors are.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">Every confirmed candidate at its real catalog position on the whole sky. Hover a point for its coordinates; click it to open the full evidence. The glowing band marks where the Milky Way lies along the galactic plane.</p>
      </div>
      {points.length === 0 ? (
        <p className="text-xs text-faint">Run export_dashboard.py to add sky positions.</p>
      ) : (
        <div className="rounded-xl border border-line bg-panel p-4 sm:p-6">
          <SkyMap points={points} className="mx-auto w-full max-w-[1700px]" />
        </div>
      )}
    </main>
  );
}
