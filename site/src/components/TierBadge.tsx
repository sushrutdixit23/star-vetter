import { TIER_STYLE } from "@/lib/tiers";
import type { Tier } from "@/lib/types";

export default function TierBadge({ tier }: { tier: Tier }) {
  const s = TIER_STYLE[tier];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${s.text} ${s.bg} ${s.border}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
