"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

// A number that counts up the first time it scrolls into view. The server
// (and any visitor with JavaScript off, or who asks for reduced motion) gets
// the final value straight away, so the text is never wrong and never empty.
// The width is reserved from the final value so nothing shifts while it runs.

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

function format(n: number, decimals: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export default function CountUp({
  value,
  decimals = 0,
  suffix = "",
  duration = 1300,
  className = "",
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  duration?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  const finalText = format(value, decimals) + suffix;

  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setShown(0); // before the first paint, so there is no flash of the final value
    let raf = 0;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        const t0 = performance.now();
        const tick = (now: number) => {
          const p = Math.min(1, (now - t0) / duration);
          const eased = p === 1 ? 1 : 1 - Math.pow(2, -10 * p); // ease-out expo
          setShown(value * eased);
          if (p < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [value, duration]);

  return (
    <span
      ref={ref}
      className={className}
      style={{ display: "inline-block", minWidth: `${finalText.length}ch`, fontVariantNumeric: "tabular-nums" }}
      aria-label={finalText}
    >
      <span aria-hidden="true">{format(shown, decimals)}{suffix}</span>
    </span>
  );
}
