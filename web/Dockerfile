# ── Stage 1: install dependencies ──────────────────────────────────────────
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# ── Stage 2: build production assets ───────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

# ── Stage 3: serve compiled assets ─────────────────────────────────────────
# Uses `vite preview` — serves the compiled dist/ folder with no dev tooling,
# no HMR, and no source maps. The development override (docker-compose.override.yml)
# bind-mounts source and replaces this CMD with `npm run dev` for local work.
FROM node:20-alpine

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
# Copy all files needed for both production (preview) and dev-override (npm run dev)
COPY package.json vite.config.ts tsconfig.json index.html ./
COPY src ./src

EXPOSE 3000

CMD ["npm", "run", "preview"]
