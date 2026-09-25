import type { ActivityEvent, FunnelStep, RunInfo } from "@/lib/types";

// Run history and the activity feed are parsed straight out of the
// orchestrator's own log files (data/logs/orchestrator_*.log) by
// export_dashboard.py. The log has no per-line clock times, so events are
// labelled by the stage they came from.

const STAGE_COLORS = ["#38bdf8", "#60a5fa", "#a78bfa", "#f472b6", "#fbbf24", "#34d399"];

export function fmtStamp(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mon = d.toLocaleString("en-GB", { month: "short" });
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${mon} ${d.getFullYear()}, ${hh}:${mm}`;
}

export function fmtRuntime(min: number | null): string {
  if (min === null) return "-";
  if (min < 60) return `${min.toFixed(1)} min`;
  const h = Math.floor(min / 60);
  return `${h}h ${String(Math.round(min - h * 60)).padStart(2, "0")}m`;
}

function statusClass(s: string) {
  if (s === "Completed") return "border-emerald-400/30 bg-emerald-400/10 text-emerald-300";
  if (s === "Stopped") return "border-amber-400/30 bg-amber-400/10 text-amber-300";
  return "border-rose-400/30 bg-rose-400/10 text-rose-300";
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`rounded border px-1.5 py-px text-[10px] ${statusClass(status)}`}>{status}</span>;
}

const SHORT: Record<string, string> = {
  "Targets sampled and fetch attempted": "sampled",
  "Usable light curve obtained": "usable",
  "Passed statistical vetting gates": "stat. passing",
  "Flagged novel (no catalog match)": "novel",
  "Survived contamination check, pixel-checked": "pixel-checked",
  "Confirmed on-target": "confirmed",
};

export function LatestRun({
  run,
  funnel,
  runsLogged,
}: {
  run: RunInfo;
  funnel: FunnelStep[];
  runsLogged: number;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-muted">#{run.id}</span>
          <span className="text-faint">{fmtStamp(run.started)}</span>
          <StatusPill status={run.status} />
        </div>
        <div className="mt-3 flex h-1.5 gap-1">
          {funnel.map((s, i) => (
            <div key={s.label} className="flex-1 rounded-full" style={{ background: STAGE_COLORS[i % STAGE_COLORS.length] }} />
          ))}
        </div>
        <dl className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-6">
          {funnel.map((s) => (
            <div key={s.label}>
              <dd className="font-mono text-base text-fg">{s.count.toLocaleString("en-US")}</dd>
              <dt className="text-[10px] text-muted">{SHORT[s.label] ?? s.label}</dt>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-[10px] text-faint">
          Counts are cumulative across every run to date, as of this run.
        </p>
      </div>
      <dl className="grid min-w-44 grid-cols-2 gap-x-4 gap-y-1 rounded-lg border border-line bg-panel-2 p-3 text-[11px] lg:grid-cols-1">
        <Row k="Runtime" v={fmtRuntime(run.runtime_min)} />
        <Row k="New targets" v={run.targets_drawn !== null ? String(run.targets_drawn) : "-"} />
        <Row k="Stage retries" v={String(run.retries)} />
        <Row k="Runs logged" v={String(runsLogged)} />
      </dl>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{k}</dt>
      <dd className="font-mono text-fg">{v}</dd>
    </div>
  );
}

export function RunsTable({ runs }: { runs: RunInfo[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="text-faint">
          <tr>
            <th className="py-1.5 pr-2 font-normal">Run</th>
            <th className="py-1.5 pr-2 font-normal">Started</th>
            <th className="py-1.5 pr-2 text-right font-normal">New</th>
            <th className="py-1.5 pr-2 text-right font-normal">Confirmed</th>
            <th className="py-1.5 pr-2 font-normal">Status</th>
            <th className="py-1.5 text-right font-normal">Runtime</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {runs.slice(0, 6).map((r) => (
            <tr key={r.id}>
              <td className="py-1.5 pr-2 font-mono text-muted">{r.id.slice(2)}</td>
              <td className="py-1.5 pr-2 text-fg">{fmtStamp(r.started)}</td>
              <td className="py-1.5 pr-2 text-right font-mono text-fg">{r.targets_drawn ?? "-"}</td>
              <td className="py-1.5 pr-2 text-right font-mono text-fg">{r.confirmed_total ?? "-"}</td>
              <td className="py-1.5 pr-2"><StatusPill status={r.status} /></td>
              <td className="py-1.5 text-right font-mono text-muted">{fmtRuntime(r.runtime_min)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] text-faint">
        Confirmed = total confirmed to date when that run finished. Parsed from the orchestrator logs.
      </p>
    </div>
  );
}

export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <ol className="max-h-72 space-y-2 overflow-y-auto pr-1 font-mono text-[11px] leading-snug">
      {[...events].reverse().map((e, i) => (
        <li key={i} className="grid grid-cols-[auto_1fr] gap-2">
          <span
            className={`mt-1 h-1.5 w-1.5 rounded-full ${
              e.kind === "fail" ? "bg-rose-400" : e.kind === "ok" ? "bg-emerald-400" : "bg-sky-400"
            }`}
          />
          <div>
            <span className="text-faint">{e.stage}</span>
            <p className={e.kind === "decision" ? "text-fg/90" : "text-muted"}>{e.text}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
