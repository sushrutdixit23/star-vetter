"use client";

import { useEffect, useRef, useState } from "react";
import { GLOSSARY, type GlossaryId } from "@/lib/glossary";

// Click-to-reveal definition for a technical term. Click, not hover, so it
// works the same on a phone as a desktop. If the id isn't in the glossary
// this just renders the plain label - it never breaks the page it's used in.
export default function Term({
  id,
  children,
}: {
  id: GlossaryId | string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const entry = GLOSSARY[id];

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!entry) return <>{children}</>;

  return (
    <span ref={wrapRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="cursor-pointer border-b border-dotted border-white/40 text-inherit decoration-inherit hover:border-accent hover:text-accent focus:border-accent focus:text-accent focus:outline-none"
      >
        {children}
      </button>
      {open && (
        <span
          role="note"
          className="absolute left-0 top-full z-50 mt-2 w-64 rounded-lg border border-line bg-panel-2 p-3 text-left text-[11px] font-sans font-normal normal-case leading-relaxed tracking-normal text-muted shadow-xl"
        >
          <span className="mb-1 block text-xs font-semibold text-fg">{entry.term}</span>
          {entry.def}
        </span>
      )}
    </span>
  );
}
