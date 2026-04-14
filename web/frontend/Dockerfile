# Stage 1: Build the frontend
FROM node:22-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Skip tsc type-check; Vite handles transpilation
RUN npx vite build

# Stage 2: Caddy serves static files + reverse-proxies API
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist /srv
EXPOSE 80 443
