import type { Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";

// A schematic, not-to-scale diagram of two orbiting stars. Colour marks
// which tier the detection carries - it is not a measurement of either
// star's true temperature, colour, or relative size, which this pipeline
// does not derive (see "V. Caveats" - no physical model).
export default function OrbitSchematic({
  tier,
  className = "",
}: {
  tier: Tier;
  className?: string;
}) {
  const primary = TIER_STYLE[tier].chart;
  const secondary = "#c9c4b8";
  return (
    <svg
      viewBox="0 0 320 160"
      className={className}
      role="img"
      aria-label="Schematic diagram of two orbiting stars, not to scale"
    >
      <ellipse
        cx="160"
        cy="80"
        rx="130"
        ry="34"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeDasharray="2 6"
      />
      <circle cx="130" cy="80" r="26" fill={primary} />
      <circle cx="230" cy="92" r="15" fill={secondary} />
    </svg>
  );
}
