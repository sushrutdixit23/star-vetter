"use client";

/* eslint-disable @next/next/no-img-element */
import { useState } from "react";
import Link from "next/link";
import type { Detail, Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";
import { percentile } from "@/lib/colormap";
import { fmtDec, fmtRA } from "@/lib/sky";
import TierBadge from "../TierBadge";
import ExtLink from "../ExtLink";
import Term from "../Term";
import Heatmap from "./Heatmap";
import { OCChart, PhaseScatter } from "./charts";
import { IconDownload, IconExternal, IconQuote, IconShare } from "../icons";

// Everything the dashboard shows about ONE candidate. `s` is the small
// summary every candidate ships with (from export_site_data.py); `d` is the
// heavier science export (export_dashboard.py), loaded on demand, and may be
// null if that script has not been run - each panel then says so.

export interface Summary {
  tic: number;
  tier: Tier;
  caveats: { tier: Tier; text: string }[];
  period_days: number;
  corrected_period_days: number | null;
  aliased: boolean;
  depth_frac: number;
  duration_days: number;
  bls_snr: number;
  odd_even_z: number | null;
  pixel: {
    sector: number;
    diff_peak_snr: number;
    centroid_offset_px: number;
    centroid_offset_arcsec: number;
    t0_shift_phase: number;
    compactness: number;
    nearest: { tic: number; dist_px: number; dtmag: number } | null;
    image: string;
  };
  catalogs: { name: string; matched: boolean }[];
  binned: [number, number | null][];
}

const pct = (x: number, d = 3) => `${(x * 100).toFixed(d)}%`;
const f = (x: number | null | undefined, d = 2) =>
  x === null || x === undefined || !Number.isFinite(x) ? "-" : x.toFixed(d);

export function Card({
  title,
  aside,
  children,
  className = "",
}: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`min-w-0 rounded-xl border border-line bg-panel p-4 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-medium text-fg">{title}</h3>
        {aside && <div className="text-[11px] text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

function StatRow({ k, v, sub, term }: { k: string; v: string; sub?: string; term?: string }) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-3 border-b border-line py-1">
      <dt className="text-muted">{term ? <Term id={term}>{k}</Term> : k}</dt>
      <dd className="text-right font-mono text-fg">
        {v}
        {sub && <span className="ml-1.5 text-faint">{sub}</span>}
      </dd>
    </div>
  );
}

function summaryLine(s: Summary, d: Detail | null) {
  const P = d ? d.period_true_days : s.corrected_period_days ?? s.period_days;
  const parts = [`${P.toFixed(4)}-day period`];
  if (d?.aliased || s.aliased) parts[0] += " (twice the BLS period)";
  if (d?.primary) parts.push(`a ${pct(d.primary.depth, 2)} primary eclipse`);
  if (d?.secondary) {
    parts.push(
      d.secondary.detected
        ? `a ${pct(d.secondary.depth, 2)} secondary eclipse at phase ${d.secondary.phase.toFixed(3)}`
        : "no significant secondary eclipse"
    );
  }
  const base = `Eclipsing-binary candidate: ${parts.join(", ")}.`;
  return d && d.checks.length > 0 ? `${base} Automated cross-checks question this period - see below.` : base;
}

export function DetailHeader({
  s,
  d,
  hasDossier,
}: {
  s: Summary;
  d: Detail | null;
  hasDossier: boolean;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = async (what: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopied("failed");
    }
  };
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const url = `${origin}/candidates/${s.tic}`;
  const P = d ? d.period_true_days : s.corrected_period_days ?? s.period_days;
  const cite = `TIC ${s.tic}, eclipsing-binary candidate, P = ${P.toFixed(5)} d. Star Vetter automated vetting of TESS data (${new Date().getFullYear()}). ${url}`;
  const btn =
    "inline-flex items-center gap-1.5 rounded-md border border-line bg-panel-2 px-2.5 py-1.5 text-xs text-fg hover:border-accent/60";
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-2xl text-fg sm:text-3xl">TIC {s.tic}</h2>
        <TierBadge tier={s.tier} />
      </div>
      <p className="mt-1 text-sm text-muted">{summaryLine(s, d)}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={btn} onClick={() => copy("cite", cite)}>
          <IconQuote className="h-3.5 w-3.5" /> {copied === "cite" ? "Copied" : "Cite"}
        </button>
        <ExtLink className={btn} href={d ? `/data/detail/TIC${s.tic}.json` : `/data/candidates/TIC${s.tic}.json`} download>
          <IconDownload className="h-3.5 w-3.5" /> Data (JSON)
        </ExtLink>
        {hasDossier && (
          <ExtLink className={btn} href={`/dossiers/TIC${s.tic}_dossier.pdf`} newTab>
            <IconDownload className="h-3.5 w-3.5" /> Dossier (PDF)
          </ExtLink>
        )}
        <button type="button" className={btn} onClick={() => copy("share", url)}>
          <IconShare className="h-3.5 w-3.5" /> {copied === "share" ? "Link copied" : "Share"}
        </button>
        <Link className={btn} href={`/candidates/${s.tic}`}>
          Full page
        </Link>
      </div>
      {d && d.checks.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {d.checks.map((c, i) => (
            <li key={i} className="rounded-md border border-rose-400/40 bg-rose-400/10 px-2.5 py-1.5 text-[11px] leading-snug text-fg/90">
              <span className="mr-1 font-medium text-rose-300">Cross-check:</span>
              {c}
            </li>
          ))}
        </ul>
      )}
      {s.caveats.some((c) => c.tier !== "CLEAN") && (
        <ul className="mt-3 space-y-1.5">
          {s.caveats
            .filter((c) => c.tier !== "CLEAN")
            .map((c, i) => (
              <li key={i} className={`rounded-md border px-2.5 py-1.5 text-[11px] leading-snug ${TIER_STYLE[c.tier].border} ${TIER_STYLE[c.tier].bg} text-fg/85`}>
                <span className={`mr-1 font-medium ${TIER_STYLE[c.tier].text}`}>{TIER_STYLE[c.tier].label}:</span>
                {c.text}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}

export function StatsTable({ s, d }: { s: Summary; d: Detail | null }) {
  const c = d?.catalog ?? {};
  const sec = d?.secondary;
  const secText = !sec
    ? "-"
    : sec.detected
      ? `${pct(sec.depth, 2)} +/- ${pct(sec.err, 2)}`
      : `< ${pct(Math.max(sec.depth, 0) + 5 * sec.err, 2)}`;
  const secSub = !sec
    ? undefined
    : sec.detected
      ? `phase ${sec.phase.toFixed(3)}, ${f(sec.sigma, 0)} sigma`
      : "none at 5 sigma";
  return (
    <dl className="text-[12px]">
      <StatRow k="Period (true)" v={`${(d ? d.period_true_days : s.corrected_period_days ?? s.period_days).toFixed(5)} d`} term="period_true" />
      <StatRow
        k="Period (BLS)"
        v={`${s.period_days.toFixed(5)} d`}
        sub={s.aliased ? "alias" : "same"}
        term="period_bls"
      />
      <StatRow
        k="Primary eclipse depth"
        v={d?.primary ? `${pct(d.primary.depth, 2)} +/- ${pct(d.primary.err, 2)}` : pct(s.depth_frac, 2)}
        sub={d ? `seen ${d.epochs.seen}/${d.epochs.covered}` : "BLS"}
        term="depth"
      />
      <StatRow k="Secondary eclipse depth" v={secText} sub={secSub} term="secondary_eclipse" />
      <StatRow k="Odd/even depth z" v={f(s.odd_even_z, 2)} sub={s.aliased ? "> 3: alias" : "< 3"} term="odd_even" />
      <StatRow
        k="Sinusoid check (Lomb-Scargle)"
        v={d?.periodicity ? `${d.periodicity.ls_period_days.toFixed(4)} d` : "-"}
        sub={d?.periodicity ? `power ${d.periodicity.ls_power.toFixed(2)}${d.periodicity.flag ? " - FLAG" : ""}` : undefined}
        term="lomb_scargle"
      />
      <StatRow k="Eclipse duration (BLS box)" v={`${(s.duration_days * 24).toFixed(1)} h`} term="duration" />
      <StatRow
        k="Distance (TIC, Gaia-based)"
        v={c.dist_pc ? `${c.dist_pc.toFixed(0)} pc` : "-"}
        sub={c.dist_err_pc ? `+/- ${c.dist_err_pc.toFixed(0)}` : undefined}
      />
      <StatRow k="Gaia G / TESS mag" v={`${f(c.gaia_g, 2)} / ${f(c.tmag, 2)}`} term="tess_mag" />
      <StatRow
        k="Teff / radius (TIC)"
        v={`${c.teff_k ? c.teff_k.toFixed(0) + " K" : "-"} / ${c.radius_rsun ? c.radius_rsun.toFixed(2) + " Rsun" : "-"}`}
        term="teff"
      />
      <StatRow
        k="RA / Dec (J2000)"
        v={c.ra !== null && c.ra !== undefined && c.dec !== null && c.dec !== undefined ? `${fmtRA(c.ra)}  ${fmtDec(c.dec)}` : "-"}
      />
      <StatRow k="BLS SNR / pixel SNR" v={`${f(s.bls_snr, 1)} / ${f(s.pixel.diff_peak_snr, 1)}`} term="snr" />
      <StatRow
        k="Light curve"
        v={d ? `${d.n_points.toLocaleString("en-US")} pts` : "-"}
        sub={d ? `over ${d.baseline_days.toFixed(0)} d` : undefined}
        term="light_curve"
      />
    </dl>
  );
}

export function EclipseProfiles({ s, d }: { s: Summary; d: Detail | null }) {
  const color = TIER_STYLE[s.tier].chart;
  if (!d || !d.zoom.primary) {
    return <p className="text-xs text-faint">Run export_dashboard.py to add the eclipse close-ups.</p>;
  }
  const z = [d.zoom.primary, d.zoom.secondary];
  const all = z.flatMap((q) => (q ? q.raw.map((p) => p[1]) : []));
  const lines = z.flatMap((q) => (q ? q.binned.map((p) => p[1]) : []));
  const lo = Math.min(percentile(all, 0.5), ...lines);
  const hi = Math.max(percentile(all, 99.5), ...lines);
  const pad = (hi - lo) * 0.08;
  const yd: [number, number] = [lo - pad, hi + pad];
  return (
    <div className="grid grid-cols-2 gap-3">
      {(["primary", "secondary"] as const).map((k, i) => {
        const q = z[i];
        const m = k === "primary" ? d.primary : d.secondary;
        return (
          <div key={k} className="min-w-0 rounded-lg border border-line bg-panel-2 p-2">
            <div className="mb-1 flex items-baseline justify-between text-[11px]">
              <span className="text-fg">
                {k === "primary" ? "Primary eclipse" : `Secondary (phase ${(d.fold.second_phase ?? 0.5).toFixed(3)})`}
              </span>
              <span className="font-mono text-muted">
                {m ? (k === "secondary" && d.secondary && !d.secondary.detected ? "not sig." : pct(m.depth, 2)) : "-"}
              </span>
            </div>
            {q ? (
              <PhaseScatter
                raw={q.raw}
                line={q.binned}
                xDomain={[-q.half_width_h, q.half_width_h]}
                yDomain={yd}
                height={170}
                color={color}
                xLabel="hours from mid-eclipse"
                xTickCount={3}
                compact
              />
            ) : (
              <p className="text-[11px] text-faint">no data at this phase</p>
            )}
          </div>
        );
      })}
      <p className="col-span-2 text-[10px] text-faint">
        Same flux scale on both panels. Line: binned median. Shown in place of an orbit animation - this
        pipeline measures eclipses, it does not fit an orbit.
      </p>
    </div>
  );
}

export function LightCurvePanel({ s, d }: { s: Summary; d: Detail | null }) {
  const color = TIER_STYLE[s.tier].chart;
  if (!d) {
    return <p className="text-xs text-faint">Run export_dashboard.py to add the full light curve.</p>;
  }
  return (
    <div>
      <div className="mb-1 flex flex-wrap gap-3 text-[10px] text-muted">
        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: color }} /> observed</span>
        <span className="inline-flex items-center gap-1"><span className="h-0.5 w-3 bg-slate-100" /> binned median</span>
        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-violet-400" /> residuals</span>
      </div>
      <PhaseScatter
        raw={d.fold.raw}
        line={d.fold.binned}
        resid={d.fold.resid}
        height={250}
        color={color}
        xLabel={`phase (P = ${d.period_true_days.toFixed(4)} d)`}
        yLabel="relative flux"
      />
      <p className="mt-1 text-[10px] text-faint">
        Residual scatter {d.fold.resid_rms !== null ? pct(d.fold.resid_rms, 3) : "-"} (observed minus binned median).
      </p>
    </div>
  );
}

export function AliasPanel({ s, d }: { s: Summary; d: Detail | null }) {
  if (!d) return <p className="text-xs text-faint">Run export_dashboard.py to add the alias check.</p>;
  const z = d.odd_even_z;
  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        {([
          ["bls", `BLS period ${d.period_bls_days.toFixed(4)} d`, "#fb7185"],
          ["double", `2x BLS ${(2 * d.period_bls_days).toFixed(4)} d`, "#7dd3fc"],
        ] as const).map(([k, label, col]) => (
          <div key={k} className="min-w-0">
            <div className="mb-0.5 text-[10px] text-muted">{label}</div>
            <PhaseScatter raw={d.alias[k].raw} line={d.alias[k].binned} height={120} color={col} compact xTickCount={2} />
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-[11px] text-muted">
        Odd/even depth z = <span className="font-mono text-fg">{f(z, 2)}</span>
        {s.aliased ? (
          <>
            {" "}(gate 3.0): alternate eclipses differ, so the true period is{" "}
            <span className="font-mono text-fg">2 x {d.period_bls_days.toFixed(4)} = {d.period_true_days.toFixed(4)} d</span>.
          </>
        ) : (
          <> (gate 3.0): alternate eclipses match, so the BLS period stands.</>
        )}
      </p>
    </div>
  );
}

export function PixelEvidence({ s, d }: { s: Summary; d: Detail | null }) {
  const m = d?.pixel_maps ?? null;
  const p = s.pixel;
  const stats = (
    <dl className="text-[11px]">
      <StatRow k="Difference-image peak SNR" v={f(p.diff_peak_snr, 1)} term="difference_imaging" />
      <StatRow k="Centroid offset" v={`${f(p.centroid_offset_px, 2)} px`} sub={`${f(p.centroid_offset_arcsec, 0)}"`} term="centroid_offset" />
      <StatRow k="Epoch shift" v={`${f(p.t0_shift_phase, 4)} phase`} term="epoch" />
      <StatRow
        k="Nearest capable neighbour"
        v={p.nearest ? `TIC ${p.nearest.tic}` : "none"}
        sub={p.nearest ? `${f(p.nearest.dist_px, 2)} px, dT ${f(p.nearest.dtmag, 1)}` : undefined}
        term="contamination"
      />
      <StatRow k="Compactness" v={f(p.compactness, 2)} term="compactness" />
      <StatRow k="TESS sector" v={String(p.sector)} term="sector" />
    </dl>
  );
  if (!m) {
    return (
      <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
        <img src={p.image} alt={`Pixel-level difference imaging for TIC ${s.tic}`} className="w-full rounded border border-line" />
        {stats}
      </div>
    );
  }
  const inn = m.out.map((row, j) => row.map((v, i) => (v === null || m.diff[j][i] === null ? null : v - (m.diff[j][i] as number))));
  const flux = [...m.out.flat(), ...inn.flat()].filter((v): v is number => v !== null);
  const lo = percentile(flux, 1);
  const hi = percentile(flux, 99.5);
  const dv = m.diff.flat().filter((v): v is number => v !== null);
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_15rem]">
      <div>
        <div className="grid grid-cols-3 gap-2">
          <Heatmap grid={m.out} lo={lo} hi={hi} stretch="sqrt" target={m.target} neighbours={m.neighbours} label="Out of eclipse" />
          <Heatmap grid={inn} lo={lo} hi={hi} stretch="sqrt" target={m.target} neighbours={m.neighbours} label="In eclipse" />
          <Heatmap grid={m.diff} lo={percentile(dv, 1)} hi={Math.max(...dv)} target={m.target} centroid={m.centroid} neighbours={m.neighbours} label="Difference (out - in)" />
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
          <span><span className="font-bold text-rose-400">+</span> target TIC {s.tic}</span>
          <span><span className="font-bold text-lime-400">x</span> neighbour bright enough to cause the dip</span>
          <span><span className="text-cyan-300">o</span> other TIC stars</span>
          <span><span className="text-yellow-300">O</span> dimming centroid</span>
          <span>1 pixel = 21&quot;</span>
        </div>
        <p className="mt-1 text-[10px] text-faint">
          Out/in share one sqrt colour scale; in-eclipse = out-of-eclipse minus difference. TESS sector {m.sector}.
        </p>
      </div>
      {stats}
    </div>
  );
}

export function TimingPanel({ d }: { d: Detail | null }) {
  if (!d) return <p className="text-xs text-faint">Run export_dashboard.py to add eclipse timing.</p>;
  const t = d.timing;
  const pts = t.points.filter((p): p is { epoch: number; oc_min: number; err_min: number } => p.oc_min !== null);
  if (pts.length < 3) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-line p-4 text-center text-xs text-muted">
        {t.note ?? "Not enough fully covered eclipses to test the timing."}
      </div>
    );
  }
  const flat = t.chi2_red !== null && t.chi2_red !== undefined && t.chi2_red < 2;
  return (
    <div>
      <OCChart points={pts} />
      <p className="mt-1 text-[11px] text-muted">
        {t.n} eclipses timed, rms {f(t.rms_min, 2)} min, reduced chi-square {f(t.chi2_red, 2)} ({t.dof} dof):{" "}
        {flat ? "consistent with a constant period." : "more scatter than the timing errors explain - worth a closer look."}
      </p>
      <p className="text-[10px] text-faint">
        Each eclipse timed by fitting the star&apos;s own mean eclipse profile; fitted P = {f(t.period_fit_days, 6)} +/- {f(t.period_fit_err_days, 6)} d.
      </p>
    </div>
  );
}

export function CatalogPanel({ s }: { s: Summary }) {
  return (
    <div>
      <ul className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        {s.catalogs.map((c) => (
          <li key={c.name} className="flex justify-between gap-2 border-b border-line py-1.5 text-[11px]">
            <span className="text-fg">{c.name}</span>
            <span className={c.matched ? "text-amber-300" : "text-emerald-300"}>{c.matched ? "Matched" : "Not found"}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-faint">
        {s.catalogs.filter((c) => c.matched).length}/{s.catalogs.length} catalogs list a known variable at this position.
      </p>
    </div>
  );
}

export function QuickActions({ s, d, hasDossier }: { s: Summary; d: Detail | null; hasDossier: boolean }) {
  const b = "flex items-center justify-between gap-2 rounded-md border border-line bg-panel-2 px-3 py-2 text-xs text-fg hover:border-accent/60";
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
      {hasDossier && (
        <ExtLink className={b} href={`/dossiers/TIC${s.tic}_dossier.pdf`} newTab>
          Full dossier (PDF) <IconDownload className="h-3.5 w-3.5 text-muted" />
        </ExtLink>
      )}
      <ExtLink className={b} href={d ? `/data/detail/TIC${s.tic}.json` : `/data/candidates/TIC${s.tic}.json`} download>
        Download data (JSON) <IconDownload className="h-3.5 w-3.5 text-muted" />
      </ExtLink>
      <ExtLink className={b} href={`https://exofop.ipac.caltech.edu/tess/target.php?id=${s.tic}`} newTab>
        Open in ExoFOP <IconExternal className="h-3.5 w-3.5 text-muted" />
      </ExtLink>
      <ExtLink className={b} href={`https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html?searchQuery=TIC%20${s.tic}`} newTab>
        Open in MAST <IconExternal className="h-3.5 w-3.5 text-muted" />
      </ExtLink>
    </div>
  );
}
