# syntax=docker/dockerfile:1.6
# AutoCSR frontend — Vite/Vue 3 build, served by nginx.
#
#   stage 1 (builder) — npm install + npm run build → /app/dist
#   stage 2 (runtime) — copy dist into nginx:alpine + custom nginx.conf
# ---------------------------------------------------------------------------

ARG NODE_VERSION=20

# ------------------------------ builder ------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --prefer-offline; \
    else npm install --no-audit; fi
COPY . .
RUN npm run build

# ------------------------------ runtime ------------------------------------
FROM nginx:1.27-alpine AS runtime
RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O- http://127.0.0.1/healthz >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
