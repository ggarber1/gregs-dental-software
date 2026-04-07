# ── Dependencies ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps

RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

WORKDIR /app

# Copy workspace manifests for dependency resolution
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY packages/config/typescript/package.json ./packages/config/typescript/
COPY packages/config/prettier/package.json ./packages/config/prettier/
COPY packages/config/eslint/package.json ./packages/config/eslint/
COPY packages/shared-types/package.json ./packages/shared-types/
COPY packages/ui/package.json ./packages/ui/
COPY apps/web/package.json ./apps/web/

RUN pnpm install --frozen-lockfile

# ── Builder ───────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages/config/eslint/node_modules ./packages/config/eslint/node_modules
COPY --from=deps /app/packages/shared-types/node_modules ./packages/shared-types/node_modules
COPY --from=deps /app/packages/ui/node_modules ./packages/ui/node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules

# Copy source
COPY packages/ packages/
COPY apps/web/ apps/web/
COPY turbo.json .

# Build-time config — NEXT_PUBLIC_* vars are baked into the JS bundle by next build.
# Values are passed as --build-arg from the deploy workflow (read from SSM).
ARG NEXT_PUBLIC_COGNITO_USER_POOL_ID
ARG NEXT_PUBLIC_COGNITO_CLIENT_ID
ARG NEXT_PUBLIC_COGNITO_REGION=us-east-1
ARG NEXT_PUBLIC_API_URL

ENV NEXT_PUBLIC_COGNITO_USER_POOL_ID=$NEXT_PUBLIC_COGNITO_USER_POOL_ID \
    NEXT_PUBLIC_COGNITO_CLIENT_ID=$NEXT_PUBLIC_COGNITO_CLIENT_ID \
    NEXT_PUBLIC_COGNITO_REGION=$NEXT_PUBLIC_COGNITO_REGION \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Build shared packages first, then web
RUN pnpm --filter @dental/shared-types build
RUN pnpm --filter @dental/ui build
RUN pnpm --filter @dental/web build

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

WORKDIR /app

COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/public ./apps/web/public

USER nextjs

EXPOSE 3000

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

CMD ["node", "apps/web/server.js"]
