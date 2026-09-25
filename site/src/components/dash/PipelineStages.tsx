/* eslint-disable @next/next/no-img-element */
import MiniChart from "../MiniChart";
import Heatmap from "./Heatmap";
import {
  IconSample,
  IconFetch,
  IconVet,
  IconCatalog,
  IconNeighbours,
  IconPixel,
  IconDossier,
} from "../icons";
import type { Candidate, Detail, FunnelStep } from "@/lib/types";
import { percentile } from "@/lib/colormap";

// The seven pipeline stages with the cumulative count that survived each,
// taken from the funnel export_pipeline_stats.py computes. Thumbnails are
// drawn from the featured candidate's own data.
const L = {
  sampled: "Targets sampled and fetch attempted",
  usable: "Usable light curve obtained",
  passing: "Passed statistical vetting gates",
  novel: "Flagged novel (no catalog match)",
  pixel: "Survived contamination check, pixel-checked",
  confirmed: "Confirmed on-target",
};

export default function PipelineStages({
  funnel,
  catalogs,
  featured,
  detail,
  dossiers,
}: {
  funnel: FunnelStep[];
  catalogs: string[];
  featured: Candidate;
  detail: Detail | null;
  dossiers: number | null;
}) {
  const n = (label: string) => funnel.find((s) => s.label === label)?.count;
  const S = n(L.sampled);
  const U = n(L.usable);
  const V = n(L.passing);
  const N = n(L.novel);
  const X = n(L.pixel);
  const C = n(L.confirmed);
  const minus = (a?: number, b?: number, what = "") =>
    a !== undefined && b !== undefined ? `-${(a - b).toLocaleString("en-US")} ${what}` : "";
  const matched = featured.novelty.catalogs.filter((c) => c.matched).length;
  const maps = detail?.pixel_maps ?? null;

  let pixelThumb: React.ReactNode = (
    <img src={featured.pixel_check.image} alt="" className="h-full w-full object-cover" />
  );
  if (maps) {
    const vals = maps.diff.flat().filter((v): v is number => v !== null);
    pixelThumb = (
      <div className="w-14">
        <Heatmap
          grid={maps.diff}
          lo={percentile(vals, 1)}
          hi={percentile(vals, 99.5)}
          target={maps.target}
          centroid={maps.centroid}
          neighbours={[]}
          label=""
        />
      </div>
    );
  }

  const stages = [
    { n: "01", title: "Sample", count: S, icon: IconSample, sub: "Fresh TIC targets", note: S !== undefined ? "stratified draw" : "",
      thumb: <SampleThumb /> },
    { n: "02", title: "Fetch", count: U, icon: IconFetch, sub: "TESS light curves", note: minus(S, U, "no usable data"),
      thumb: <RawThumb raw={featured.light_curve.raw} /> },
    { n: "03", title: "Vet", count: V, icon: IconVet, sub: "BLS + physical gates", note: minus(U, V, "rejected"),
      thumb: <MiniChart binned={detail ? detail.fold.binned : featured.light_curve.binned} height={48} color="#7dd3fc" /> },
    { n: "04", title: "Catalogs", count: N, icon: IconCatalog, sub: `${catalogs.length} catalogs`, note: minus(V, N, "already known"),
      thumb: (
        <div className="text-center leading-tight">
          <div className="font-mono text-base text-emerald-300">{matched}/{catalogs.length}</div>
          <div className="text-[9px] text-faint">matches</div>
        </div>
      ) },
    { n: "05", title: "Neighbours", count: X, icon: IconNeighbours, sub: "Variable neighbours", note: minus(N, X, "contaminated"),
      thumb: (
        <div className="text-center leading-tight">
          <div className="font-mono text-base text-fg">{maps ? maps.neighbours.length : "-"}</div>
          <div className="text-[9px] text-faint">stars in cutout</div>
        </div>
      ) },
    { n: "06", title: "Pixel", count: C, icon: IconPixel, sub: "Difference imaging", note: minus(X, C, "not confirmed"),
      thumb: pixelThumb },
    { n: "07", title: "Dossier", count: dossiers ?? C, icon: IconDossier, sub: "Written up", note: "PDF per star",
      thumb: <DossierThumb /> },
  ];

  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
      {stages.map((s) => (
        <li key={s.n} className="flex flex-col rounded-lg border border-line bg-panel-2 p-2">
          <div className="font-mono text-[10px] text-faint">{s.n}</div>
          <div className="text-[13px] font-medium leading-tight text-fg">{s.title}</div>
          <div className="mt-0.5 flex items-center justify-between">
            <span className="font-mono text-lg text-accent">
              {s.count !== undefined ? s.count.toLocaleString("en-US") : "-"}
            </span>
            <s.icon className="hidden h-4 w-4 text-muted 2xl:block" />
          </div>
          <div className="mt-1.5 flex h-14 items-center justify-center overflow-hidden rounded border border-line bg-canvas">
            {s.thumb}
          </div>
          <div className="mt-1.5 text-[10px] leading-snug text-muted">{s.sub}</div>
          <div className={`font-mono text-[10px] leading-snug ${s.note.startsWith("-") ? "text-rose-300/80" : "text-faint"}`}>
            {s.note}
          </div>
        </li>
      ))}
    </ol>
  );
}

function RawThumb({ raw }: { raw: [number, number][] }) {
  const w = 120;
  const h = 56;
  const ys = raw.map((p) => p[1]);
  const lo = percentile(ys, 0.5);
  const hi = percentile(ys, 99.5);
  const span = hi - lo || 1;
  const step = Math.max(1, Math.floor(raw.length / 400));
  const pts = raw.filter((_, i) => i % step === 0);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" preserveAspectRatio="none">
      {pts.map((p, i) => (
        <circle
          key={i}
          cx={(p[0] + 0.5) * (w - 8) + 4}
          cy={Math.max(2, Math.min(h - 2, h - 4 - ((p[1] - lo) / span) * (h - 8)))}
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
