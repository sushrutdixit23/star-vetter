import { ImageResponse } from "next/og";
import { getPipelineStats } from "@/lib/data";

// The link-preview card (LinkedIn, Slack, iMessage...). Generated at build
// time from the pipeline's own funnel, so it updates after every run. The
// dot galaxy uses the same grouping as the homepage hero: sizes to scale,
// positions illustrative.

export const alt = "Star Vetter - an unattended pipeline that hunts for eclipsing binary stars in NASA TESS data";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const DOTS = 420;

export default function Image() {
  const funnel = getPipelineStats()?.funnel ?? [];
  const counts = funnel.slice(0, 6).map((s) => s.count);
  const ready = counts.length === 6 && counts[0] > 0;
  const [S, U, V, N, X, C] = ready ? counts : [1, 1, 1, 1, 1, 1];
  const groups: [number, string][] = [
    [C, "#f4f1ea"],
    [Math.max(X - C, 0), "#ff7262"],
    [Math.max(N - X, 0), "#c9c4b8"],
    [Math.max(V - N, 0), "#ffb061"],
    [Math.max(U - V, 0), "#93b9ff"],
    [Math.max(S - U, 0), "#3d4358"],
  ];
  const scale = DOTS / S;
  const per = groups.map(([n]) => (n === 0 ? 0 : Math.max(1, Math.round(n * scale))));
  const total = per.reduce((a, b) => a + b, 0) || 1;
  const r = rng(20260927);
  const dots: { x: number; y: number; s: number; c: string; glow: boolean }[] = [];
  let i = 0;
  groups.forEach(([, c], gi) => {
    for (let k = 0; k < per[gi]; k++) {
      const rad = 265 * Math.sqrt((i + 0.5) / total);
      const th = i * GOLDEN + r() * 0.35;
      const s = gi === 0 ? 7 : 3 + r() * 4;
      dots.push({ x: Math.round(900 + rad * Math.cos(th) - s / 2), y: Math.round(315 + rad * Math.sin(th) - s / 2), s: Math.round(s), c, glow: gi === 0 });
      i++;
    }
  });
  const stat = ready ? `${S.toLocaleString("en-US")} targets examined  /  ${C.toLocaleString("en-US")} survivors` : "Eclipsing binaries from NASA TESS data";

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", position: "relative", background: "#07090f", color: "#f4f1ea" }}>
        {dots.map((d, j) => (
          <div key={j} style={{ position: "absolute", left: d.x, top: d.y, width: d.s, height: d.s, borderRadius: 9999, background: d.c, opacity: d.glow ? 1 : 0.85, boxShadow: d.glow ? "0 0 14px 4px rgba(255,248,230,0.55)" : "none" }} />
        ))}
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "60px 64px", width: 660, height: "100%" }}>
          <div style={{ display: "flex", fontSize: 22, letterSpacing: 8, color: "#cfd3dd" }}>STAR VETTER</div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", fontSize: 54, lineHeight: 1.1 }}>I built a machine that hunts for new binary stars, then tries to kill everything it finds.</div>
            <div style={{ display: "flex", marginTop: 24, fontSize: 24, lineHeight: 1.35, color: "#9aa0b2" }}>An unattended pipeline vetting NASA TESS stars for eclipsing binaries - every number from the pipeline itself.</div>
          </div>
          <div style={{ display: "flex", fontSize: 22, color: "#93b9ff" }}>{stat}</div>
        </div>
      </div>
    ),
    size
  );
}
