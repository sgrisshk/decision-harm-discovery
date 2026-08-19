FROM node:22.18.0-alpine AS deps
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM node:22.18.0-alpine AS builder
RUN corepack enable
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter web build

# Static export (output: "export", see apps/web/next.config.ts) — no Node server, no API/DB
# colocated. This image is a container-hosted alternative to the GitHub Pages deploy
# (.github/workflows/pages.yml) for local dev (docker-compose.yml) and for anyone who'd rather
# self-host than use Pages; both serve the exact same `out/` artifact.
FROM node:22.18.0-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
WORKDIR /app
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/out ./out
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/scripts/static-server.mjs ./scripts/static-server.mjs
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["wget", "-q", "--spider", "http://127.0.0.1:3000"]
CMD ["node", "scripts/static-server.mjs", "out", "3000"]
