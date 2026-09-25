"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

// TIC lookup. An exact match jumps straight to that candidate's dossier;
// anything else opens the candidate browser pre-filtered. Press "/" anywhere
// to focus it.
export default function HeaderSearch({ tics }: { tics: number[] }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      const typing =
        t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = value.trim().replace(/^tic\s*/i, "");
    if (!q) return;
    const n = Number(q);
    if (Number.isInteger(n) && tics.includes(n)) {
      router.push(`/candidates/${n}`);
    } else {
      router.push(`/candidates?q=${encodeURIComponent(q)}`);
    }
    setValue("");
    inputRef.current?.blur();
  }

  return (
    <form onSubmit={submit} className="relative w-72">
      <svg
        viewBox="0 0 20 20"
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
      >
        <circle cx="9" cy="9" r="5.5" />
        <path d="M13.2 13.2 17 17" />
      </svg>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search by TIC ID"
        aria-label="Search by TIC ID"
        inputMode="numeric"
        className="w-full rounded-lg border border-line bg-panel py-2 pl-9 pr-9 text-sm text-fg placeholder:text-faint focus:border-accent/60 focus:outline-none"
      />
      <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-line px-1.5 font-mono text-[10px] text-faint">
        /
      </kbd>
    </form>
  );
}
