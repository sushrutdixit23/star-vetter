import type { ReactNode } from "react";

/**
 * Keeps a wide SVG chart at a legible size on a phone: below `min` pixels the
 * chart stops shrinking and scrolls sideways instead, so axis text never drops
 * under about 8 px.
 */
export default function ScrollX({ children, min = 600 }: { children: ReactNode; min?: number }) {
  return (
    <div>
      <div className="overflow-x-auto overscroll-x-contain pb-1" tabIndex={0} role="group" aria-label="Chart, scrolls sideways on small screens">
        <div style={{ minWidth: min }}>{children}</div>
      </div>
      <p className="mt-1 font-mono text-[11px] text-faint sm:hidden" aria-hidden="true">Swipe sideways for the whole chart</p>
    </div>
  );
}
