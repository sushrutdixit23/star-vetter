"use client";

import { useSyncExternalStore } from "react";

// Days until a fixed UTC date. Rendered as the plain date on the server and first paint, then filled in.
export default function Countdown({ iso, label }: { iso: string; label: string }) {
  // null on the server and first paint, the live count afterwards
  const days = useSyncExternalStore(
    () => () => {},
    () => Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000),
    () => null,
  );
  return (
    <div>
      <div className="font-display text-6xl leading-none text-fg sm:text-7xl">{days === null ? "\u2014" : days > 0 ? days : 0}</div>
      <div className="mt-2 font-mono text-[11px] text-muted">{days !== null && days <= 0 ? "released: run the steps" : `days to ${label}`}</div>
    </div>
  );
}
