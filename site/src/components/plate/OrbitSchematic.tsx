import { useId } from "react";
import type { Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";

// A schematic, not-to-scale diagram of two orbiting stars. Colour marks
// which tier the detection carries - it is not a measurement of either
// star's true temperature, colour, or relative size, which this pipeline
// does not derive (see "V. Caveats" - no physical model). The gradient is
// a lit-sphere illustration, not a rendering of either star's real
// brightness profile.
export default function OrbitSchematic({
  tier,
  className = "",
}: {
  tier: Tier;
  className?: string;
}) {
  const uid = useId();
  const primary = TIER_STYLE[tier].chart;
  const secondary = "#c9c4b8";
  return (
    <svg
      viewBox="0 0 320 160"
      className={className}
      role="img"
      aria-label="Schematic diagram of two orbiting stars, not to scale"
    >
      <defs>
        <radialGradient id={`orbit-primary-${uid}`} cx="35%" cy="32%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="45%" stopColor={primary} />
          <stop offset="100%" stopColor={primary} stopOpacity="0.85" />
        </radialGradient>
        <radialGradient id={`orbit-secondary-${uid}`} cx="35%" cy="32%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="50%" stopColor={secondary} />
          <stop offset="100%" stopColor={secondary} stopOpacity="0.85" />
        </radialGradient>
      </defs>
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
      <circle cx="130" cy="80" r="26" fill={`url(#orbit-primary-${uid})`} />
      <circle cx="230" cy="92" r="15" fill={`url(#orbit-secondary-${uid})`} />
    </svg>
  );
}
