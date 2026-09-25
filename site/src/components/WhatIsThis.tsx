"use client";

import { useState } from "react";
import Link from "next/link";

// A click-to-expand plain-English explainer for the hero. Collapsed by
// default so it doesn't compete with the headline; expands in place so
// there's no navigation required to get an answer to "what is this?".
export default function WhatIsThis() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-5 max-w-md">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full border border-white/25 px-3 py-1.5 text-xs text-white/70 hover:border-accent/70 hover:text-accent"
      >
        <span aria-hidden className="text-[13px] leading-none">{open ? "-" : "+"}</span>
        What is this, in plain terms?
      </button>
      {open && (
        <div className="mt-3 space-y-3 rounded-lg border border-white/10 bg-black/30 p-4 text-sm leading-relaxed text-white/75 backdrop-blur">
          <p className="m-0">
            TESS has photographed hundreds of millions of stars, and only a
            small fraction have ever been individually checked by a person.
            This is software that checks the rest on its own: it looks for
            two stars orbiting so closely that each one dims the other&apos;s
            light on a repeating schedule, runs a battery of statistical and
            pixel-level checks to rule out noise and false alarms, and writes
            up every survivor with the evidence attached - unattended, start
            to finish.
          </p>
          <p className="m-0">
            <Link href="/about" className="text-accent hover:underline">
              Read the full methodology
            </Link>{" "}
            or{" "}
            <Link href="/glossary" className="text-accent hover:underline">
              look up a term
            </Link>
            .
          </p>
        </div>
      )}
    </div>
  );
}
