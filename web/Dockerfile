FROM node:22-alpine AS deps
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
# NEXT_PUBLIC_* values are inlined at build time, so the token is a build arg.
ARG NEXT_PUBLIC_LEDGER_ADMIN_TOKEN=
ENV NEXT_PUBLIC_LEDGER_ADMIN_TOKEN=$NEXT_PUBLIC_LEDGER_ADMIN_TOKEN
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
RUN apk upgrade --no-cache
ENV NODE_ENV=production
ENV PORT=8080
COPY --from=builder /app ./
EXPOSE 8080
CMD ["npm", "start"]
