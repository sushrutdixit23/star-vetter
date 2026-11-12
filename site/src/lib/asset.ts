// Prefix for files in public/ when the site is served under a sub-path (static export on GitHub Pages).
// next/link and next/router add the base path themselves; plain file URLs (downloads, PDFs) do not.
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export function asset(path: string): string {
  return path.startsWith("/") ? BASE + path : path;
}
