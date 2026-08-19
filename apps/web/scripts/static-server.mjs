#!/usr/bin/env node
// Zero-dependency static file server for the `next build` static export (output: "export",
// trailingSlash: true — see next.config.ts). Used by `pnpm start` and infra/docker/web.Dockerfile.
//
// `serve`/`http-server`/etc. were considered and rejected: every one of them drags in
// `serve-handler` -> an unmaintained old `minimatch`, three high-severity CVEs
// (GHSA-7r86-cg39-jmmj and friends) that `pnpm audit --audit-level=high` — already a CI gate,
// .github/workflows/ci.yml's frontend job — flags. Serving a folder of prebuilt HTML/CSS/JS with
// trailing-slash resolution doesn't need a dependency at all.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const root = process.argv[2] ?? "out";
const port = Number(process.argv[3] ?? process.env.PORT ?? 3000);

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function resolveFile(urlPath) {
  // Reject any path that would escape `root` after normalization (e.g. "/../../etc/passwd").
  const safePath = normalize(join(root, decodeURIComponent(urlPath))).replace(/^(\.\.[/\\])+/, "");
  const candidates = urlPath.endsWith("/")
    ? [join(safePath, "index.html")]
    : [safePath, `${safePath}.html`, join(safePath, "index.html")];
  for (const candidate of candidates) {
    if (existsSync(candidate) && statSync(candidate).isFile()) {
      return candidate;
    }
  }
  return null;
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  const file = resolveFile(url.pathname) ?? join(root, "404.html");
  const status = file.endsWith("404.html") && resolveFile(url.pathname) === null ? 404 : 200;
  res.writeHead(status, { "Content-Type": CONTENT_TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
});

server.listen(port, () => {
  console.log(`Serving ${root} at http://localhost:${port}`);
});
