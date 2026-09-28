"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Old shared links pointed at /?tic=N (the former homepage explorer). The
// candidate page is now the canonical view of a star, so forward there.
export default function TicRedirect() {
  const router = useRouter();
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tic");
    if (t && /^[0-9]+$/.test(t)) router.replace(`/candidates/${t}`);
  }, [router]);
  return null;
}
