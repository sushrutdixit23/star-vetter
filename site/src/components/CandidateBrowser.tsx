"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import CandidateCard, { type CardData } from "./CandidateCard";
import { TIER_ORDER, TIER_STYLE } from "@/lib/tiers";
import type { Tier } from "@/lib/types";

type SortKey = "bls_snr" | "pixel_snr" | "period" | "depth";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "bls_snr", label: "BLS SNR" },
  { key: "pixel_snr", label: "Pixel SNR" },
  { key: "period", label: "Period" },
  { key: "depth", label: "Depth" },
];

export default function CandidateBrowser({ cards }: { cards: CardData[] }) {
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [tier, setTier] = useState<Tier | "ALL">("ALL");
  const [sort, setSort] = useState<SortKey>("bls_snr");

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

  return (
    <div>
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
        </div>
      </div>

      {shown.length === 0 ? (
        <p className="rounded-xl border border-line bg-panel p-8 text-center text-sm text-muted">
          No confirmed candidate matches that filter.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((c) => (
            <CandidateCard key={c.tic} c={c} />
          ))}
        </div>
      )}
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
