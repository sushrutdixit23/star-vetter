import { useId } from "react";

// A radiant star in SVG. Glow layers (added together with screen blending,
// so they brighten like light rather than paint): a wide faint haze, a
// strong bloom with a white-hot centre (gently pulsing), a bright ring at
// the surface, and optional light spikes. Then the disk (white-hot centre
// fading to a cooler, darker rim - limb darkening and reddening), a slowly
// churning surface texture, a hot core highlight and the limb shading.
// "radiance" scales the glow (the caller drives it from the real light
// curve); "dim" below 1 darkens the whole star, for a companion seen
// against a brighter star in transit.
export default function StarBody({ cx, cy, r, color, edge, glow = 1, flare = false, texture = true, dim = 1, radiance = 1 }: { cx: number; cy: number; r: number; color: string; edge?: string; glow?: number; flare?: boolean; texture?: boolean; dim?: number; radiance?: number }) {
  const id = useId();
  const rim = edge ?? color;
  const glowOpacity = Math.round(Math.min(1, Math.max(0.12, dim) * radiance) * 100) / 100;
  const freq = (2.6 / Math.max(r, 1)).toFixed(3);
  return (
    <g>
      <defs>
        <radialGradient id={`${id}-haze`}>
          <stop offset="0%" style={{ stopColor: color }} stopOpacity={0.22} />
          <stop offset="100%" style={{ stopColor: color }} stopOpacity={0} />
        </radialGradient>
        <radialGradient id={`${id}-bloom`}>
          <stop offset="0%" stopColor="#ffffff" stopOpacity={0.9} />
          <stop offset="12%" style={{ stopColor: color }} stopOpacity={0.7} />
          <stop offset="35%" style={{ stopColor: color }} stopOpacity={0.25} />
          <stop offset="60%" style={{ stopColor: rim }} stopOpacity={0.08} />
          <stop offset="100%" style={{ stopColor: rim }} stopOpacity={0} />
        </radialGradient>
        <radialGradient id={`${id}-corona`}>
          <stop offset="58%" style={{ stopColor: color }} stopOpacity={1} />
          <stop offset="72%" style={{ stopColor: color }} stopOpacity={0.55} />
          <stop offset="100%" style={{ stopColor: rim }} stopOpacity={0} />
        </radialGradient>
        <radialGradient id={`${id}-disk`} cx="46%" cy="44%" r="60%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="30%" style={{ stopColor: color }} />
          <stop offset="82%" style={{ stopColor: rim }} />
          <stop offset="100%" style={{ stopColor: rim }} />
        </radialGradient>
        <radialGradient id={`${id}-core`}>
          <stop offset="0%" stopColor="#ffffff" stopOpacity={0.85} />
          <stop offset="30%" stopColor="#ffffff" stopOpacity={0} />
        </radialGradient>
        <radialGradient id={`${id}-limb`}>
          <stop offset="62%" stopColor="#000000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000000" stopOpacity={0.4} />
        </radialGradient>
        <radialGradient id={`${id}-spike`}>
          <stop offset="0%" stopColor="#ffffff" stopOpacity={1} />
          <stop offset="20%" style={{ stopColor: color }} stopOpacity={0.7} />
          <stop offset="100%" style={{ stopColor: color }} stopOpacity={0} />
        </radialGradient>
        <filter id={`${id}-grain`} x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency={freq} numOctaves={3} seed={11} />
          <feColorMatrix type="matrix" values="0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0 0 0 0 1" />
        </filter>
        <clipPath id={`${id}-clip`}>
          <circle cx={cx} cy={cy} r={r} />
        </clipPath>
      </defs>
      <g opacity={glowOpacity} style={{ mixBlendMode: "screen" }}>
        <circle cx={cx} cy={cy} r={r * 6.5 * glow} fill={`url(#${id}-haze)`} />
        <circle cx={cx} cy={cy} r={r * 3.8 * glow} fill={`url(#${id}-bloom)`} className="sv-twinkle" />
        <circle cx={cx} cy={cy} r={r * 1.45} fill={`url(#${id}-corona)`} />
        {flare && (
          <g className="sv-twinkle">
            <ellipse cx={cx} cy={cy} rx={r * 5.2} ry={r * 0.045} fill={`url(#${id}-spike)`} />
            <ellipse cx={cx} cy={cy} rx={r * 0.045} ry={r * 5.2} fill={`url(#${id}-spike)`} />
            <ellipse cx={cx} cy={cy} rx={r * 3} ry={r * 0.03} fill={`url(#${id}-spike)`} opacity={0.5} transform={`rotate(45 ${cx} ${cy})`} />
            <ellipse cx={cx} cy={cy} rx={r * 3} ry={r * 0.03} fill={`url(#${id}-spike)`} opacity={0.5} transform={`rotate(-45 ${cx} ${cy})`} />
          </g>
        )}
      </g>
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id}-disk)`} />
      {texture && (
        <g clipPath={`url(#${id}-clip)`}>
          <rect x={cx - r} y={cy - r} width={r * 2} height={r * 2} filter={`url(#${id}-grain)`} opacity={0.28} className="sv-spin" style={{ mixBlendMode: "overlay" }} />
        </g>
      )}
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id}-core)`} />
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id}-limb)`} />
      {dim < 1 && <circle cx={cx} cy={cy} r={r} fill="#05070c" opacity={Math.round((1 - dim) * 70) / 100} />}
    </g>
  );
}
