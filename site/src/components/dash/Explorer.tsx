"use client";

import { useEffect, useRef, useState } from "react";
import type { Detail, Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";
import MiniChart from "../MiniChart";
import TierBadge from "../TierBadge";
import {
  AliasPanel,
  Card,
  CatalogPanel,
  DetailHeader,
  EclipseProfiles,
  LightCurvePanel,
  PixelEvidence,
  QuickActions,
  StatsTable,
  TimingPanel,
  type Summary,
} from "./DetailPanels";

// The interactive half of the home page: pick a candidate on the left and
// every panel updates to that star. Detail data is fetched on demand from
// /data/detail/TIC{n}.json (static files), so the page stays light.

type Group = "all" | "clean" | "alias" | "flagged";
const GROUPS: { key: Group; label: string; test: (t: Tier) => boolean }[] = [
  { key: "all", label: "All", test: () => true },
  { key: "clean", label: "Clean", test: (t) => t === "CLEAN" },
  { key: "alias", label: "Period alias", test: (t) => t === "PERIOD ALIAS" },
  { key: "flagged", label: "Flagged", test: (t) => t !== "CLEAN" && t !== "PERIOD ALIAS" },
];
const PAGE = 6;

export default function Explorer({
  summaries,
  initialTic,
  initialDetail,
  dossiers,
  runsSlot,
  activitySlot,
}: {
  summaries: Summary[];
  initialTic: number;
  initialDetail: Detail | null;
  dossiers: number[];
  runsSlot?: React.ReactNode;
  activitySlot?: React.ReactNode;
}) {
  const [tic, setTic] = useState(initialTic);
  const [cache, setCache] = useState<Record<number, Detail | null>>({ [initialTic]: initialDetail });
  const [group, setGroup] = useState<Group>("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"snr" | "period" | "depth">("snr");
  const [page, setPage] = useState(0);
  const topRef = useRef<HTMLDivElement>(null);

  const select = (t: number, scroll = false) => {
    setTic(t);
    if (typeof window !== "undefined") {
      const u = new URL(window.location.href);
      u.searchParams.set("tic", String(t));
      window.history.replaceState(null, "", u.toString());
    }
    if (scroll) topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // honour ?tic=... on first load (shared links)
  useEffect(() => {
    const t = Number(new URLSearchParams(window.location.search).get("tic"));
    if (!t || t === initialTic || !summaries.some((s) => s.tic === t)) return;
    const id = setTimeout(() => setTic(t), 0);
    return () => clearTimeout(id);
  }, [summaries, initialTic]);

  useEffect(() => {
    if (tic in cache) return;
    let live = true;
    fetch(`/data/detail/TIC${tic}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((d: Detail | null) => {
        if (!live) return;
        setCache((c) => ({ ...c, [tic]: d }));
      });
    return () => {
      live = false;
    };
  }, [tic, cache]);

  const s = summaries.find((x) => x.tic === tic) ?? summaries[0];
  const d = cache[tic] ?? null;
  const loading = !(tic in cache);
  const hasDossier = dossiers.includes(s.tic);

  const g = GROUPS.find((x) => x.key === group)!;
  const filtered = summaries
    .filter((x) => g.test(x.tier))
    .filter((x) => (q.trim() ? String(x.tic).includes(q.trim()) : true))
    .sort((a, b) =>
      sort === "snr"
        ? b.bls_snr - a.bls_snr
        : sort === "period"
          ? (a.corrected_period_days ?? a.period_days) - (b.corrected_period_days ?? b.period_days)
          : b.depth_frac - a.depth_frac
    );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const pg = Math.min(page, pages - 1);
  const shown = filtered.slice(pg * PAGE, pg * PAGE + PAGE);

  return (
    <div ref={topRef} className="grid scroll-mt-20 grid-cols-1 gap-4 xl:grid-cols-12">
      {/* ---------------- list ---------------- */}
      <section className="min-w-0 rounded-xl border border-line bg-panel p-4 xl:col-span-3">
        <h2 className="display-caps text-sm font-semibold text-fg">Candidates</h2>
        <p className="mt-1 text-xs text-muted">{summaries.length} confirmed on-target. Pick one to inspect it.</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {GROUPS.map((x) => {
            const n = summaries.filter((c) => x.test(c.tier)).length;
            if (n === 0 && x.key !== "all") return null;
            return (
              <button
                key={x.key}
                type="button"
                onClick={() => {
                  setGroup(x.key);
                  setPage(0);
                }}
                className={`rounded-md border px-2 py-1 text-[11px] ${
                  group === x.key ? "border-fg/60 bg-fg text-canvas" : "border-line text-muted hover:text-fg"
                }`}
              >
                {x.label} ({n})
              </button>
            );
          })}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
            placeholder="Search TIC ID"
            inputMode="numeric"
            className="min-w-0 flex-1 rounded-md border border-line bg-panel-2 px-2 py-1.5 text-xs text-fg placeholder:text-faint focus:border-accent/60 focus:outline-none"
          />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as "snr" | "period" | "depth")}
            className="rounded-md border border-line bg-panel-2 px-1.5 py-1.5 text-xs text-fg"
            aria-label="Sort"
          >
            <option value="snr">BLS SNR</option>
            <option value="period">Period</option>
            <option value="depth">Depth</option>
          </select>
        </div>
        <ul className="mt-3 space-y-1.5">
          {shown.map((c) => {
            const on = c.tic === tic;
            return (
              <li key={c.tic}>
                <button
                  type="button"
                  onClick={() => select(c.tic)}
                  className={`grid w-full grid-cols-[4.5rem_1fr_auto] items-center gap-2.5 rounded-lg border p-2 text-left transition-colors ${
                    on ? "border-accent/70 bg-panel-2" : "border-line hover:border-fg/30"
                  }`}
                >
                  <div className="h-9 rounded border border-line bg-canvas p-0.5">
                    <MiniChart binned={c.binned} height={32} color={TIER_STYLE[c.tier].chart} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-xs text-fg">TIC {c.tic}</span>
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-muted">
                      P = {(c.corrected_period_days ?? c.period_days).toFixed(4)} d
                    </div>
                    <div className="font-mono text-[10px] text-muted">Depth = {(c.depth_frac * 100).toFixed(2)}%</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <TierBadge tier={c.tier} />
                    <span className="font-mono text-[10px] text-faint">SNR {Math.round(c.bls_snr).toLocaleString("en-US")}</span>
                  </div>
                </button>
              </li>
            );
          })}
          {shown.length === 0 && <li className="py-6 text-center text-xs text-faint">No candidates match.</li>}
        </ul>
        <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
          <button type="button" disabled={pg === 0} onClick={() => setPage(pg - 1)} className="rounded border border-line px-2 py-1 disabled:opacity-40">
            Previous
          </button>
          <span>
            Page {pg + 1} of {pages}
          </span>
          <button type="button" disabled={pg >= pages - 1} onClick={() => setPage(pg + 1)} className="rounded border border-line px-2 py-1 disabled:opacity-40">
            Next
          </button>
        </div>
      </section>

      {/* ---------------- selected candidate ---------------- */}
      <section className={`min-w-0 rounded-xl border border-line bg-panel p-4 transition-opacity xl:col-span-5 ${loading ? "opacity-60" : ""}`}>
        <DetailHeader s={s} d={d} hasDossier={hasDossier} />
        <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <StatsTable s={s} d={d} />
          <EclipseProfiles s={s} d={d} />
        </div>
      </section>

      <div className={`grid min-w-0 gap-4 xl:col-span-4 ${loading ? "opacity-60" : ""}`}>
        <Card title="Light curve" aside="phase folded at the true period">
          <LightCurvePanel s={s} d={d} />
        </Card>
        <Card title="Period alias analysis">
          <AliasPanel s={s} d={d} />
        </Card>
      </div>

      {/* ---------------- second row ---------------- */}
      <Card title="Runs" aside="from the orchestrator logs" className="xl:col-span-3">
        {runsSlot}
      </Card>
      <Card
        title="Pixel evidence"
        aside={`TESS sector ${s.pixel.sector}`}
        className={`xl:col-span-5 ${loading ? "opacity-60" : ""}`}
      >
        <PixelEvidence s={s} d={d} />
      </Card>
      <Card title="O - C timing" aside="primary eclipses" className={`xl:col-span-4 ${loading ? "opacity-60" : ""}`}>
        <TimingPanel d={d} />
      </Card>

      {/* ---------------- third row ---------------- */}
      <Card title="Latest run activity" aside="orchestrator decisions" className="xl:col-span-4">
        {activitySlot}
      </Card>
      <Card title="Catalog cross-match" aside={`TIC ${s.tic}`} className="xl:col-span-5">
        <CatalogPanel s={s} />
      </Card>
      <Card title="Quick actions" className="xl:col-span-3">
        <QuickActions s={s} d={d} hasDossier={hasDossier} />
      </Card>
    </div>
  );
}
