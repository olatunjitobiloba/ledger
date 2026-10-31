FROM node:22-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
RUN apk upgrade --no-cache
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_BACKEND_URL=https://ledger.rumptycloud.app
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

# Upgrade base OS packages and replace bundled npm with a minimal shim
# to eliminate vendor CVEs while satisfying PaaS start commands ("npm start")
RUN apk upgrade --no-cache && \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx && \
    printf '#!/bin/sh\ncase "$1" in\n  -v|--version|version)\n    echo "10.9.0"\n    ;;\n  *)\n    exec node server.js\n    ;;\nesac\n' > /usr/local/bin/npm && \
    chmod 755 /usr/local/bin/npm && \
    ln -s /usr/local/bin/npm /usr/local/bin/npx

ENV NODE_ENV=production
ENV PORT=8080
ENV HOSTNAME="0.0.0.0"

# Copy minimal standalone build and assets (excludes all devDependencies and unpruned node_modules)
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 8080
CMD ["node", "server.js"]
