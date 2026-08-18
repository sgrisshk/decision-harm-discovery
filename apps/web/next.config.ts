import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Deployed to GitHub Pages (static hosting only — no Node server, no API/DB
  // colocated). Every route that needs live data now fetches it client-side
  // against NEXT_PUBLIC_API_URL, baked in at build time. See
  // .github/workflows/pages.yml and docs/operations/deployment.md.
  output: "export",
  trailingSlash: true,
  poweredByHeader: false,
};

export default nextConfig;
