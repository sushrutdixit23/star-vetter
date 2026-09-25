import Link from "next/link";
import TierBadge from "./TierBadge";
import MiniChart from "./MiniChart";
import { TIER_STYLE } from "@/lib/tiers";
import { fmtNum, fmtDepth } from "@/lib/format";
import type { Tier } from "@/lib/types";

// Slim shape so the client-side candidate browser only ships what a card
// needs (not the 2500-point raw scatter).
export interface CardData {
  tic: number;
  tier: Tier;
  period_days: number;
  corrected_period_days: number | null;
  depth_frac: number;
  bls_snr: number;
  pixel_snr: number;
  binned: [number, number | null][];
}

export default function CandidateCard({ c }: { c: CardData }) {
  const period = c.corrected_period_days ?? c.period_days;
  return (
    <Link
      href={`/candidates/${c.tic}`}
      className="group block rounded-xl border border-line bg-panel p-4 transition hover:border-accent/40"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-faint">TIC</div>
          <div className="font-mono text-lg font-semibold text-fg">{c.tic}</div>
        </div>
        <TierBadge tier={c.tier} />
      </div>

      <div className="mt-3">
        <MiniChart binned={c.binned} color={TIER_STYLE[c.tier].chart} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div className="flex justify-between border-b border-line pb-1">
          <dt className="text-faint">Period</dt>
          <dd className="font-mono text-fg/80">{fmtNum(period, 3)}d</dd>
        </div>
        <div className="flex justify-between border-b border-line pb-1">
          <dt className="text-faint">Depth</dt>
          <dd className="font-mono text-fg/80">{fmtDepth(c.depth_frac)}</dd>
        </div>
        <div className="flex justify-between border-b border-line pb-1">
          <dt className="text-faint">BLS SNR</dt>
          <dd className="font-mono text-fg/80">{fmtNum(c.bls_snr, 0)}</dd>
        </div>
        <div className="flex justify-between border-b border-line pb-1">
          <dt className="text-faint">Pixel SNR</dt>
          <dd className="font-mono text-fg/80">{fmtNum(c.pixel_snr, 1)}</dd>
        </div>
      </dl>
    </Link>
  );
}
