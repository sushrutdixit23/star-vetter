import { ImageResponse } from "next/og";
import { getAllTics, getDetail } from "@/lib/data";
import { tempColor, tempRgb } from "@/lib/starColor";

// Per-candidate share card (link previews, LinkedIn, Slack). Built at build
// time from the star's own pipeline output; nothing is invented. It says
// "candidate, not confirmed" and never "discovery".

export const alt = "A TESS eclipsing-binary candidate vetted by Star Vetter";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export function generateStaticParams() {
  return getAllTics().map((tic) => ({ tic: String(tic) }));
}

const fmt = (v: number, d: number) => v.toFixed(d);

export default async function Image({ params }: { params: Promise<{ tic: string }> }) {
  const { tic: ticParam } = await params;
  const tic = Number(ticParam);
  const d = getDetail(tic);
  const period = d?.period_true_days ?? null;
  const depth = d?.primary ? d.primary.depth : null;
  const durH = d ? d.duration_days * 24 : null;
  const tmag = d?.catalog?.tmag ?? null;
  const teff = d?.catalog?.teff_k ?? null;
  const base = teff ?? 5800;
  const [r, g, b] = tempRgb(base);
  const core = tempColor(base);
  const binned = d?.fold?.binned ?? [];

  // folded light curve panel
  const W = 480;
  const H = 150;
  let line = "";
  if (binned.length > 5) {
    const ys = binned.map((q) => q[1]);
    const lo = Math.min(...ys);
    const hi = Math.max(...ys);
    const span = hi - lo || 1;
    line = binned.map((q, i) => `${i === 0 ? "M" : "L"}${((q[0] + 0.5) * W).toFixed(1)},${(8 + (1 - (q[1] - lo) / span) * (H - 16)).toFixed(1)}`).join(" ");
  }

  const stats: [string, string][] = [];
  if (period !== null) stats.push(["PERIOD", `${fmt(period, period < 10 ? 3 : 2)} d`]);
  if (depth !== null) stats.push(["ECLIPSE DEPTH", `${fmt(depth * 100, depth < 0.1 ? 2 : 1)}%`]);
  if (durH !== null) stats.push(["DURATION", `${fmt(durH, 1)} h`]);
  if (tmag !== null) stats.push(["TESS MAG", fmt(tmag, 1)]);

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", position: "relative", background: "#07090f", color: "#f4f1ea" }}>
        <div style={{ display: "flex", position: "absolute", right: 80, top: 40, width: 460, height: 460, borderRadius: 9999, background: `radial-gradient(circle, rgba(${r},${g},${b},0.55) 0%, rgba(${r},${g},${b},0.18) 38%, rgba(${r},${g},${b},0) 70%)` }} />
        <div style={{ display: "flex", position: "absolute", right: 200, top: 160, width: 220, height: 220, borderRadius: 9999, background: `radial-gradient(circle at 42% 40%, #ffffff 0%, ${core} 38%, rgba(${Math.round(r * 0.6)},${Math.round(g * 0.6)},${Math.round(b * 0.6)},1) 100%)`, boxShadow: `0 0 60px 14px rgba(${r},${g},${b},0.45)` }} />
        <div style={{ display: "flex", position: "absolute", right: 150, top: 250, width: 44, height: 44, borderRadius: 9999, background: "#2a2f40", border: "2px solid #4a5169" }} />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "56px 64px", width: "100%", height: "100%" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", fontSize: 22, letterSpacing: 8, color: "#cfd3dd" }}>STAR VETTER</div>
            <div style={{ display: "flex", marginTop: 34, fontSize: 92, lineHeight: 1 }}>{`TIC ${tic}`}</div>
            <div style={{ display: "flex", marginTop: 16, fontSize: 28, color: "#9aa0b2", maxWidth: 620 }}>Eclipsing-binary candidate from NASA TESS data. Not confirmed.</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {line ? (
              <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
                <path d={line} fill="none" stroke="#93b9ff" strokeWidth={3} strokeLinejoin="round" />
              </svg>
            ) : null}
            {line ? <div style={{ display: "flex", marginTop: 6, marginBottom: 22, fontSize: 14, color: "#7d8397" }}>Folded light curve, one orbit, vertical scale stretched to fit</div> : null}
            <div style={{ display: "flex" }}>
              {stats.map(([k, v]) => (
                <div key={k} style={{ display: "flex", flexDirection: "column", marginRight: 48 }}>
                  <div style={{ display: "flex", fontSize: 16, letterSpacing: 4, color: "#7d8397" }}>{k}</div>
                  <div style={{ display: "flex", fontSize: 38, color: "#f4f1ea" }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", marginTop: 22, fontSize: 20, color: "#93b9ff" }}>star-vetter.vercel.app</div>
          </div>
        </div>
      </div>
    ),
    size
  );
}
