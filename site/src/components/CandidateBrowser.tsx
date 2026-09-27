"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import CandidateCard, { type CardData } from "./CandidateCard";
import TierBadge from "./TierBadge";
import SkyMap from "./dash/SkyMap";
import { TIER_ORDER, TIER_STYLE } from "@/lib/tiers";
import { fmtNum, fmtDepth } from "@/lib/format";
import type { SkyPoint, Tier } from "@/lib/types";

type SortKey = "bls_snr" | "pixel_snr" | "period" | "depth";
type ViewMode = "clocks" | "table" | "sky";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "bls_snr", label: "BLS SNR" },
  { key: "pixel_snr", label: "Pixel SNR" },
  { key: "period", label: "Period" },
  { key: "depth", label: "Depth" },
];

const VIEWS: { key: ViewMode; label: string }[] = [
  { key: "clocks", label: "Clocks" },
  { key: "table", label: "Table" },
  { key: "sky", label: "Sky" },
];

export default function CandidateBrowser({
  cards,
  skyPoints = [],
}: {
  cards: CardData[];
  skyPoints?: SkyPoint[];
}) {
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [tier, setTier] = useState<Tier | "ALL">("ALL");
  const [sort, setSort] = useState<SortKey>("bls_snr");
  const [view, setView] = useState<ViewMode>("clocks");

  const tiersPresent = TIER_ORDER.filter((t) => cards.some((c) => c.tier === t));

  const shown = (() => {
    const q = query.trim().replace(/^tic\s*/i, "");
    const list = cards.filter(
      (c) =>
        (tier === "ALL" || c.tier === tier) &&
        (q === "" || String(c.tic).includes(q))
    );
    const val = (c: CardData) =>
      sort === "bls_snr"
        ? c.bls_snr
        : sort === "pixel_snr"
          ? c.pixel_snr
          : sort === "period"
            ? (c.corrected_period_days ?? c.period_days)
            : c.depth_frac;
    return [...list].sort((a, b) => val(b) - val(a));
  })();

  const shownTics = new Set(shown.map((c) => c.tic));
  const shownSkyPoints = skyPoints.filter((p) => shownTics.has(p.tic));

  return (
    <div>
      <div className="mb-4 flex gap-1.5">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            onClick={() => setView(v.key)}
            className={`nav-caps rounded-md border px-3 py-1.5 text-xs transition-colors ${
              view === v.key ? "border-accent text-accent" : "border-line text-muted hover:text-fg"
            }`}
          >
            {v.label}
          </button>
        ))}
      </div>

      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          <Chip active={tier === "ALL"} onClick={() => setTier("ALL")}>
            All <span className="ml-1 text-faint">{cards.length}</span>
          </Chip>
          {tiersPresent.map((t) => (
            <Chip key={t} active={tier === t} onClick={() => setTier(t)}>
              <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${TIER_STYLE[t].dot}`} />
              {TIER_STYLE[t].label}
              <span className="ml-1 text-faint">
                {cards.filter((c) => c.tier === t).length}
              </span>
            </Chip>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by TIC"
            aria-label="Filter by TIC"
            inputMode="numeric"
            className="w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-fg placeholder:text-faint focus:border-accent/60 focus:outline-none lg:w-48"
          />
          {view !== "sky" && (
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              aria-label="Sort by"
              className="rounded-lg border border-line bg-panel px-3 py-2 text-sm text-fg focus:outline-none"
            >
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  Sort: {s.label}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {shown.length === 0 ? (
        <p className="rounded-xl border border-line bg-panel p-8 text-center text-sm text-muted">
          No confirmed candidate matches that filter.
        </p>
      ) : view === "clocks" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((c) => (
            <CandidateCard key={c.tic} c={c} />
          ))}
        </div>
      ) : view === "table" ? (
        <TableView cards={shown} sort={sort} onSort={setSort} />
      ) : (
        <div className="rounded-xl border border-line bg-panel p-4 sm:p-6">
          {shownSkyPoints.length === 0 ? (
            <p className="text-xs text-faint">No sky positions available for this filter.</p>
          ) : (
            <>
              <SkyMap points={shownSkyPoints} className="w-full" />
              <p className="mt-3 text-[11px] text-faint">
                {shownSkyPoints.length} of {shown.length} filtered candidates have a catalog
                position. Hover a point for its TIC number.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TableView({
  cards,
  sort,
  onSort,
}: {
  cards: CardData[];
  sort: SortKey;
  onSort: (s: SortKey) => void;
}) {
  const cols: { key: SortKey; label: string }[] = [
    { key: "period", label: "Period" },
    { key: "depth", label: "BLS depth" },
    { key: "bls_snr", label: "BLS SNR" },
    { key: "pixel_snr", label: "Pixel SNR" },
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-panel">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-faint">
            <th className="px-4 py-2.5 font-medium">TIC</th>
            <th className="px-4 py-2.5 font-medium">Tier</th>
            {cols.map((c) => (
              <th key={c.key} className="px-4 py-2.5 text-right font-medium">
                <button
                  type="button"
                  onClick={() => onSort(c.key)}
                  className={`nav-caps ${sort === c.key ? "text-accent" : "text-faint hover:text-fg"}`}
                >
                  {c.label}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cards.map((c) => (
            <tr key={c.tic} className="border-b border-line last:border-0 hover:bg-panel-2">
              <td className="px-4 py-2.5">
                <Link href={`/candidates/${c.tic}`} className="font-mono text-fg hover:text-accent">
                  {c.tic}
                </Link>
              </td>
              <td className="px-4 py-2.5">
                <TierBadge tier={c.tier} />
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-fg/80">
                {fmtNum(c.corrected_period_days ?? c.period_days, 3)}d
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-fg/80">{fmtDepth(c.depth_frac)}</td>
              <td className="px-4 py-2.5 text-right font-mono text-fg/80">{fmtNum(c.bls_snr, 0)}</td>
              <td className="px-4 py-2.5 text-right font-mono text-fg/80">{fmtNum(c.pixel_snr, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-full border px-3 py-1 text-xs transition ${
        active
          ? "border-accent/60 bg-accent/10 text-fg"
          : "border-line text-muted hover:text-fg"
      }`}
    >
      {children}
    </button>
  );
}
