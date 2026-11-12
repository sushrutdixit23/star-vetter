// Checks a static export (next build with STATIC_EXPORT=1) for internal links and assets that would break
// under a base path: every href/src/srcset that starts with "/" must start with the base path and point at a
// file that exists in the export. Usage: node scripts/check-export-links.mjs out /star-vetter
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";

const [outDir = "out", base = ""] = process.argv.slice(2);

function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, acc);
    else if (p.endsWith(".html")) acc.push(p);
  }
  return acc;
}

function resolves(url) {
  const path = decodeURIComponent(url.split(/[?#]/)[0]).slice(base.length) || "/";
  const candidates = [path, join(path, "index.html"), path.replace(/\/$/, "") + ".html"];
  return candidates.some((c) => existsSync(join(outDir, c)) && statSync(join(outDir, c)).isFile());
}

const bad = new Map();
const pages = walk(outDir);
const attr = /(?:href|src)="(\/[^"]*)"/g;
for (const file of pages) {
  const html = readFileSync(file, "utf8");
  for (const m of html.matchAll(attr)) {
    const url = m[1];
    if (url.startsWith("//")) continue;
    const ok = base ? url === base || url.startsWith(base + "/") ? resolves(url) : false : resolves(url);
    if (!ok) bad.set(url, (bad.get(url) ?? 0) + 1);
  }
}
console.log(`${pages.length} pages checked, ${bad.size} broken internal URLs`);
for (const [url, n] of [...bad.entries()].slice(0, 40)) console.log(`  ${url}  (${n} pages)`);
process.exit(bad.size ? 1 : 0);
