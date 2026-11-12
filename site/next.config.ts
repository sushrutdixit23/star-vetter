import type { NextConfig } from "next";

// STATIC_EXPORT=1 builds a plain static site into out/ (used by the GitHub Pages workflow, a fallback
// host while Vercel is unavailable). NEXT_PUBLIC_BASE_PATH is the sub-path the site is served under,
// e.g. "/star-vetter" for https://<user>.github.io/star-vetter/. Without these the config is unchanged.
const exportMode = process.env.STATIC_EXPORT === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = exportMode
  ? { output: "export", basePath, trailingSlash: true, images: { unoptimized: true } }
  : {};

export default nextConfig;
