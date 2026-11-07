"use client";

import { useState } from "react";

// Copy the page link and save the per-candidate share card. The card's URL
// is whatever the page's og:image meta tag says (Next adds a content hash to
// it), so nothing here hard-codes it.
export default function ShareButtons({ tic }: { tic: number }) {
  const [msg, setMsg] = useState<string | null>(null);
  const say = (m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg(null), 2500);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      say("Link copied");
    } catch {
      say("Copy failed - select the address bar");
    }
  };

  const save = async () => {
    try {
      const url = document.querySelector<HTMLMetaElement>('meta[property="og:image"]')?.content;
      if (!url) {
        say("Card not available");
        return;
      }
      const u = new URL(url, window.location.href);
      const res = await fetch(u.pathname + u.search); // same-origin path, whatever host the tag names
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `TIC${tic}-star-vetter.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch {
      say("Could not save the card");
    }
  };

  const btn = "nav-caps rounded-md border border-line px-2.5 py-1 font-mono text-[10px] text-muted transition-colors hover:text-fg";
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <button type="button" onClick={copy} className={btn}>Copy link</button>
      <button type="button" onClick={save} className={btn}>Save card</button>
      {msg && <span role="status" className="font-mono text-[10px] text-faint">{msg}</span>}
    </div>
  );
}
