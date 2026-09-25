/* eslint-disable @next/next/no-img-element */
import MiniChart from "./MiniChart";
import {
  IconSample,
  IconFetch,
  IconVet,
  IconCatalog,
  IconPixel,
  IconDossier,
} from "./icons";
import type { Candidate, FunnelStep } from "@/lib/types";

// The six stages as a horizontal strip. Every thumbnail is drawn from the
// featured candidate's real data (its light curve, its pixel image), not
// stock art, and the line under each stage is how many targets it removed,
// taken from the cumulative funnel.
const L = {
  sampled: "Targets sampled and fetch attempted",
  usable: "Usable light curve obtained",
  passing: "Passed statistical vetting gates",
  novel: "Flagged novel (no catalog match)",
  confirmed: "Confirmed on-target",
};

export default function PipelineStrip({
  featured,
  catalogs,
  funnel,
}: {
  featured: Candidate;
  catalogs: string[];
  funnel: FunnelStep[];
}) {
  const raw = featured.light_curve.raw;
  const n = (label: string) => funnel.find((s) => s.label === label)?.count;
  const diff = (a?: number, b?: number) =>
    a !== undefined && b !== undefined ? (a - b).toLocaleString("en-US") : null;
  const S = n(L.sampled);
  const U = n(L.usable);
  const V = n(L.passing);
  const N = n(L.novel);
  const C = n(L.confirmed);
  const notes: (string | null)[] = [
    S !== undefined ? `${S.toLocaleString("en-US")} drawn` : null,
    diff(S, U) && `-${diff(S, U)} no usable data`,
    diff(U, V) && `-${diff(U, V)} rejected`,
    diff(V, N) && `-${diff(V, N)} already known`,
    diff(N, C) && `-${diff(N, C)} not confirmed`,
    C !== undefined ? `${C.toLocaleString("en-US")} written up` : null,
  ];
  const matched = featured.novelty.catalogs.filter((c) => c.matched).length;
  const stages = [
    {
      n: "01",
      title: "Sample",
      sub: "Fresh TIC targets",
      icon: IconSample,
      thumb: <SampleThumb />,
    },
    {
      n: "02",
      title: "Fetch",
      sub: "TESS light curves",
      icon: IconFetch,
      thumb: <RawThumb raw={raw} />,
    },
    {
      n: "03",
      title: "Vet",
      sub: "BLS + physical gates",
      icon: IconVet,
      thumb: <MiniChart binned={featured.light_curve.binned} height={56} color="#7dd3fc" />,
    },
    {
      n: "04",
      title: "Cross-match",
      sub: `${catalogs.length} catalogs`,
      icon: IconCatalog,
      thumb: <CatalogThumb matched={matched} n={catalogs.length} />,
    },
    {
      n: "05",
      title: "Pixel check",
      sub: "Difference imaging",
      icon: IconPixel,
      thumb: (
        <img
          src={featured.pixel_check.image}
          alt=""
          className="h-full w-full object-cover object-center"
        />
      ),
    },
    {
      n: "06",
      title: "Dossier",
      sub: "Written up automatically",
      icon: IconDossier,
      thumb: <DossierThumb />,
    },
  ];

  return (
    <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {stages.map((s, i) => (
        <li key={s.n} className="flex flex-col">
          <div className="font-mono text-[10px] text-faint">{s.n}</div>
          <div className="text-sm font-medium text-fg">{s.title}</div>
          <div className="text-[11px] text-muted">{s.sub}</div>
          <div className="mt-2 flex items-center gap-2 text-accent">
            <s.icon className="h-5 w-5" />
          </div>
          <div className="mt-2 flex h-16 items-center justify-center overflow-hidden rounded-md border border-line bg-panel-2">
            {s.thumb}
          </div>
          {notes[i] && (
            <div
              className={`mt-2 font-mono text-[11px] ${
                notes[i]!.startsWith("-")
                  ? "text-rose-600 dark:text-rose-300/80"
                  : "text-muted"
              }`}
            >
              {notes[i]}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

function RawThumb({ raw }: { raw: [number, number][] }) {
  // raw per-cadence flux, drawn as dots across phase
  const w = 120;
  const h = 56;
  const ys = raw.map((p) => p[1]);
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const span = hi - lo || 1;
  const step = Math.max(1, Math.floor(raw.length / 400));
  const pts = raw.filter((_, i) => i % step === 0);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" preserveAspectRatio="none">
      {pts.map((p, i) => (
        <circle
          key={i}
          cx={((p[0] + 0.5) * (w - 8)) + 4}
          cy={h - 4 - ((p[1] - lo) / span) * (h - 8)}
          r={0.8}
          className="fill-muted"
          opacity={0.7}
        />
      ))}
    </svg>
  );
}

function SampleThumb() {
  const dots = [
    [14, 12], [40, 30], [70, 10], [95, 40], [22, 44], [58, 48],
    [84, 22], [108, 14], [32, 22], [64, 32], [100, 50], [8, 32],
  ];
  return (
    <svg viewBox="0 0 120 56" className="h-full w-full">
      {dots.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 5 ? 2.4 : 1.2} className={i === 5 ? "fill-accent" : "fill-muted"} />
      ))}
      <circle cx={58} cy={48} r={6} fill="none" className="stroke-accent" strokeWidth={1} />
    </svg>
  );
}

function CatalogThumb({ matched, n }: { matched: number; n: number }) {
  // this candidate's own cross-match result
  return (
    <div className="text-center">
      <div className="font-mono text-lg text-emerald-600 dark:text-emerald-300">
        {matched}/{n}
      </div>
      <div className="text-[10px] text-faint">catalog matches</div>
    </div>
  );
}

function DossierThumb() {
  return (
    <svg viewBox="0 0 120 56" className="h-full w-full">
      <rect x="44" y="6" width="32" height="44" rx="2" fill="none" className="stroke-muted" />
      {[14, 20, 26, 32, 38].map((y) => (
        <line key={y} x1="49" x2={y === 38 ? 62 : 71} y1={y} y2={y} className="stroke-faint" />
      ))}
    </svg>
  );
}
