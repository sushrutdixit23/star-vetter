"use client";

import { useState } from "react";
import type { NearestNeighbour, PixelMaps } from "@/lib/types";
import { percentile } from "@/lib/colormap";
import Heatmap from "../dash/Heatmap";
import Band from "./Band";

// The pixel check, shown on one real survivor. The pipeline does not keep
// pixel images for rejected candidates, so instead of staging a fake
// impostor this shows a real pass next to the real number of candidates
// that failed this exact test. In-eclipse = out-of-eclipse minus the
// difference image, the same derivation the candidate pages use.

const fmt = (n: number) => n.toLocaleString("en-US");

export default function NeighbourTest({ tic, maps, offsetPx, offsetArcsec, nearest, failed, reached }: { tic: number; maps: PixelMaps; offsetPx: number; offsetArcsec: number; nearest: NearestNeighbour | null; failed: number; reached: number }) {
  const [second, setSecond] = useState<"in" | "diff">("in");

  const inn = maps.out.map((row, j) => row.map((v, i) => {
    const d = maps.diff[j][i];
    return v === null || d === null ? null : v - d;
  }));
  const flux = [...maps.out.flat(), ...inn.flat()].filter((v): v is number => v !== null);
  const lo = percentile(flux, 1);
  const hi = percentile(flux, 99.5);
  const dv = maps.diff.flat().filter((v): v is number => v !== null);

  return (
    <Band variant="half" num="IV" title="The impostor test" lede="A TESS pixel is 21 arcseconds wide, so a neighbour's eclipse can leak into a star's light and look exactly like a real one. Subtracting the in-eclipse image from the out-of-eclipse image shows what actually dimmed." action={<p className="text-sm text-muted"><span className="mr-2 font-mono text-2xl text-accent-kill">{fmt(failed)}</span>of {fmt(reached)} candidates were not confirmed on-target here.</p>}>
      <div className="grid grid-cols-2 gap-3">
        <Heatmap grid={maps.out} lo={lo} hi={hi} stretch="sqrt" target={maps.target} neighbours={maps.neighbours} label="Out of eclipse" />
        {second === "in" ? (
          <Heatmap grid={inn} lo={lo} hi={hi} stretch="sqrt" target={maps.target} neighbours={maps.neighbours} label="In eclipse" />
        ) : (
          <Heatmap grid={maps.diff} lo={percentile(dv, 1)} hi={Math.max(...dv)} target={maps.target} centroid={maps.centroid} neighbours={maps.neighbours} label="Difference (out - in)" />
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={() => setSecond("in")} className={`nav-caps rounded-md border px-2.5 py-1 font-mono text-[10px] transition-colors ${second === "in" ? "border-accent text-accent" : "border-line text-muted hover:text-fg"}`}>In eclipse</button>
        <button type="button" onClick={() => setSecond("diff")} className={`nav-caps rounded-md border px-2.5 py-1 font-mono text-[10px] transition-colors ${second === "diff" ? "border-accent text-accent" : "border-line text-muted hover:text-fg"}`}>Difference</button>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
        <span><span className="font-bold text-rose-400">+</span> target</span>
        <span><span className="font-bold text-lime-400">x</span> neighbour bright enough to cause the dip</span>
        <span><span className="text-cyan-300">o</span> other catalogued stars</span>
        {second === "diff" && <span><span className="text-yellow-300">O</span> dimming centroid</span>}
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-faint">{`A real survivor: TIC ${tic}, TESS sector ${maps.sector}. The dimming centroid sits ${offsetPx.toFixed(2)} px (${offsetArcsec.toFixed(1)} arcsec) from the target.`} {nearest ? `The nearest catalogued neighbour bright enough to cause the dip, TIC ${nearest.tic}, is ${nearest.dist_px.toFixed(2)} px away.` : "No catalogued neighbour is bright enough to have caused the dip."}</p>
    </Band>
  );
}
