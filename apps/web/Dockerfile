FROM node:22-slim AS deps

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/cli/package.json packages/cli/package.json

RUN pnpm install --frozen-lockfile

FROM node:22-slim AS prod-deps

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/cli/package.json packages/cli/package.json

RUN pnpm install --frozen-lockfile --prod

FROM node:22-slim AS builder

WORKDIR /workspace

RUN corepack enable

COPY --from=deps /workspace/node_modules ./node_modules
COPY --from=deps /workspace/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web ./apps/web

ARG SECURE_COOKIES=true
ENV SECURE_COOKIES=${SECURE_COOKIES}

RUN pnpm --filter koda-web build

FROM node:22-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

RUN corepack enable

COPY --from=prod-deps /workspace/node_modules ./node_modules
COPY --from=prod-deps /workspace/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY --from=builder /workspace/apps/web ./apps/web

WORKDIR /app/apps/web

RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack && \
    addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextuser && \
    chown -R nextuser:nodejs /app

USER nextuser

EXPOSE 3000

CMD ["node", "server.mjs"]
