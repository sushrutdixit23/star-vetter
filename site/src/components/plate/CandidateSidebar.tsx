"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Tier } from "@/lib/types";
import { TIER_STYLE } from "@/lib/tiers";
import MiniChart from "../MiniChart";

// The candidate list beside every specimen plate. Thumbnails use each
// star's binned curve from its candidate export - the same source as the
// cards on /candidates, so the two views always agree.

export interface SidebarItem {
  tic: number;
  tier: Tier;
  period: number;
  depth: number;
  snr: number;
  binned: [number, number | null][];
}

type Group = "all" | "clean" | "alias" | "flagged";
type SortKey = "snr" | "period" | "depth";

function inGroup(g: Group, t: Tier): boolean {
  if (g === "all") return true;
  if (g === "clean") return t === "CLEAN";
  if (g === "alias") return t === "PERIOD ALIAS";
  return t !== "CLEAN" && t !== "PERIOD ALIAS";
}

export default function CandidateSidebar({ items, current }: { items: SidebarItem[]; current: number }) {
  const [group, setGroup] = useState<Group>("all");
  const [sort, setSort] = useState<SortKey>("snr");
  const [q, setQ] = useState("");
  const listRef = useRef<HTMLUListElement>(null);
  const activeRef = useRef<HTMLAnchorElement>(null);

  const shown = useMemo(() => {
    const qq = q.trim();
    const list = items.filter((c) => inGroup(group, c.tier) && (qq === "" || String(c.tic).includes(qq)));
    return [...list].sort((a, b) => (sort === "snr" ? b.snr - a.snr : sort === "period" ? a.period - b.period : b.depth - a.depth));
  }, [items, group, sort, q]);

  useEffect(() => {
    const list = listRef.current;
    const el = activeRef.current;
    if (!list || !el) return;
    list.scrollTop = Math.max(0, el.offsetTop - list.clientHeight / 2);
  }, [current]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line p-4">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full border border-fg/60" />
          <span className="nav-caps font-mono text-[11px] text-fg">Candidates</span>
        </div>
        <div className="mt-1 font-mono text-[10px] text-muted">{items.length} survivors</div>
        <div className="mt-3 grid grid-cols-3 overflow-hidden rounded-md border border-line font-mono text-[10px]">
          <Link href="/candidates?view=clocks" className="nav-caps py-1.5 text-center text-muted transition-colors hover:bg-panel-2 hover:text-fg">Clocks</Link>
          <Link href="/candidates?view=table" className="nav-caps border-x border-line py-1.5 text-center text-muted transition-colors hover:bg-panel-2 hover:text-fg">Table</Link>
          <Link href="/candidates?view=sky" className="nav-caps py-1.5 text-center text-muted transition-colors hover:bg-panel-2 hover:text-fg">Sky</Link>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <select value={group} onChange={(e) => setGroup(e.target.value as Group)} aria-label="Filter by tier" className="rounded-md border border-line bg-panel px-2 py-1.5 text-xs text-fg focus:outline-none">
            <option value="all">All tiers</option>
            <option value="clean">Clean</option>
            <option value="alias">Period alias</option>
            <option value="flagged">Flagged</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort" className="rounded-md border border-line bg-panel px-2 py-1.5 text-xs text-fg focus:outline-none">
            <option value="snr">Sort: SNR</option>
            <option value="period">Sort: period</option>
            <option value="depth">Sort: depth</option>
          </select>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search TIC ID" inputMode="numeric" aria-label="Search TIC ID" className="mt-2 w-full rounded-md border border-line bg-panel px-2.5 py-1.5 text-xs text-fg placeholder:text-faint focus:border-accent/60 focus:outline-none" />
      </div>
      <ul ref={listRef} className="relative flex-1 space-y-1 overflow-y-auto p-2">
        {shown.map((c) => {
          const on = c.tic === current;
          const st = TIER_STYLE[c.tier];
          return (
            <li key={c.tic}>
              <Link ref={on ? activeRef : undefined} href={`/candidates/${c.tic}`} aria-current={on ? "page" : undefined} className={`grid grid-cols-[4rem_1fr_auto] items-center gap-2 rounded-md border p-2 transition-colors ${on ? "border-accent/70 bg-accent/5" : "border-transparent hover:border-line"}`}>
                <div className="h-8 rounded border border-line bg-canvas p-0.5">
                  <MiniChart binned={c.binned} height={28} color={st.chart} />
                </div>
                <div className="min-w-0">
                  <div className="font-mono text-[11px] text-fg">TIC {c.tic}</div>
                  <div className="font-mono text-[10px] text-muted">P = {c.period.toFixed(4)} d</div>
                </div>
                <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-medium ${st.text} ${st.bg} ${st.border}`}>{st.label}</span>
              </Link>
            </li>
          );
        })}
        {shown.length === 0 && <li className="py-6 text-center text-xs text-faint">No candidates match.</li>}
      </ul>
      <div className="border-t border-line px-4 py-2 font-mono text-[10px] text-faint">Showing {shown.length} of {items.length}</div>
    </div>
  );
}
