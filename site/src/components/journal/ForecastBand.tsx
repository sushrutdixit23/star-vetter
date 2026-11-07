"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { PredictionStar } from "@/lib/types";
import Band from "./Band";

// The home-page teaser for /predictions: how long until TESS Year 9 starts,
// and the next dated eclipses we have committed to. The clock is read only
// after mount so the server and first client render agree.

const MS_DAY = 86400000;

function parts(ms: number): { d: number; h: number; m: number } {
  const t = Math.max(ms, 0);
  return { d: Math.floor(t / MS_DAY), h: Math.floor((t % MS_DAY) / 3600000), m: Math.floor((t % 3600000) / 60000) };
}

export interface ForecastItem {
  tic: number;
  grade: PredictionStar["grade"];
  utc: string;
  sigma_min: number;
  approximate: boolean;
}

export default function ForecastBand({ year9StartUtc, items, nStars, nEclipses, nValidated }: { year9StartUtc: string; items: ForecastItem[]; nStars: number; nEclipses: number; nValidated: number }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);
  const start = Date.parse(year9StartUtc);
  const left = now === null ? null : start - now;
  const t = left === null ? null : parts(left);

  return (
    <Band
      num="VI"
      title="The forecast"
      lede="Eclipse times written down before the data exist. When TESS Year 9 is public, each one is timed with the same code and graded, misses included."
      action={<Link href="/predictions" className="nav-caps inline-flex items-center rounded-md border border-line px-3 py-1.5 font-mono text-[11px] text-fg hover:border-accent/60">All predictions &rarr;</Link>}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
        <div className="rounded-lg border border-line bg-panel/60 p-5">
          <div className="nav-caps font-mono text-[10px] text-faint">{left !== null && left <= 0 ? "TESS Year 9 has begun" : "TESS Year 9 begins in"}</div>
          <div className="mt-3 flex items-baseline gap-4 font-display text-fg" aria-live="off">
            {t === null || (left !== null && left <= 0) ? (
              <span className="text-4xl text-faint">{t === null ? "- d" : "Sector 111"}</span>
            ) : (
              <>
                <span><span className="text-5xl leading-none">{t.d}</span><span className="ml-1 font-mono text-[11px] text-muted">d</span></span>
                <span><span className="text-3xl leading-none">{t.h}</span><span className="ml-1 font-mono text-[11px] text-muted">h</span></span>
                <span><span className="text-3xl leading-none text-muted">{t.m}</span><span className="ml-1 font-mono text-[11px] text-muted">m</span></span>
              </>
            )}
          </div>
          <p className="mt-3 text-[11px] leading-snug text-faint">Sector 111, 26 November 2026. After it, new data arrive sector by sector.</p>
          <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-3 font-mono">
            <div><dd className="text-xl text-fg">{nStars}</dd><dt className="text-[10px] text-faint">stars</dt></div>
            <div><dd className="text-xl text-fg">{nEclipses}</dd><dt className="text-[10px] text-faint">eclipses</dt></div>
            <div><dd className="text-xl text-fg">{nValidated}</dd><dt className="text-[10px] text-faint">validated</dt></div>
          </dl>
        </div>

        <ul className="divide-y divide-line rounded-lg border border-line bg-panel/60">
          {items.map((it) => (
            <li key={it.tic}>
              <Link href={`/candidates/${it.tic}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 hover:bg-panel-2/60">
                <span className="flex items-center gap-3">
                  <span className="font-mono text-sm text-fg">TIC {it.tic}</span>
                  <span className={`rounded-full border px-2 py-0.5 font-mono text-[10px] ${it.grade === "VALIDATED" ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300" : "border-line bg-panel-2 text-muted"}`}>{it.grade === "VALIDATED" ? "Validated" : "Not validated"}</span>
                </span>
                <span className="font-mono text-xs text-muted"><span className="whitespace-nowrap text-fg">{it.utc.slice(0, 16)} UTC</span> <span className="whitespace-nowrap">&plusmn; {it.sigma_min < 10 ? it.sigma_min.toFixed(1) : Math.round(it.sigma_min)} min{it.approximate ? " *" : ""}</span></span>
              </Link>
            </li>
          ))}
          <li className="px-4 py-2 font-mono text-[10px] text-faint">* sector dates interpolated, may shift by days</li>
        </ul>
      </div>
    </Band>
  );
}
