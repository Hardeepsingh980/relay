# Relay as ONE container: FalkorDB + FastAPI (uvicorn) + Next.js + Caddy.
# Build from the repo root:  docker build -f deploy/Dockerfile -t relay .
# Runtime layout: /app/backend (Python venv, editable install, so REPO_ROOT resolves to /app),
# /app/data (synthetic exports), /app/frontend (built Next.js app), /app/deploy (start.sh, Caddyfile, cache seed).
# No BuildKit cache mounts on purpose: Railway rejects cache mount ids without its own service prefix.

ARG FALKORDB_IMAGE=falkordb/falkordb:6.0.2
ARG NODE_IMAGE=node:22-bookworm-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1
ARG CADDY_IMAGE=caddy:2

FROM ${UV_IMAGE} AS uv
FROM ${CADDY_IMAGE} AS caddy

# ---------------------------------------------------------------- web build
FROM ${NODE_IMAGE} AS web
ENV NEXT_TELEMETRY_DISABLED=1 CI=1
RUN npm install -g pnpm@9.4.0 && pnpm --version
WORKDIR /web
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# Empty API base: the browser calls same-origin /api/..., which Caddy routes to uvicorn.
# Then keep production deps only, and drop the musl builds of the native packages (@next/swc, sharp):
# pnpm installs both libc variants, and the runtime image is glibc (Debian), so they are never loaded.
RUN NEXT_PUBLIC_RELAY_API="" pnpm build \
 && pnpm prune --prod \
 && find node_modules/.pnpm -mindepth 1 -maxdepth 1 -name '*musl*' -exec rm -rf {} + \
 && rm -rf .next/cache src

# ---------------------------------------------------------------- python env
# Built on the runtime base so the managed CPython and wheels match its glibc.
FROM ${FALKORDB_IMAGE} AS py
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
WORKDIR /app/backend
COPY backend/.python-version backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv python install "$(cat .python-version)" \
 && uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
# Editable install of `relay` (the default): config.REPO_ROOT = parents[3] of src/relay/config.py = /app.
RUN uv sync --frozen --no-dev && .venv/bin/relay --help >/dev/null

# ---------------------------------------------------------------- runtime
FROM ${FALKORDB_IMAGE}

# git clones public GitHub repos at runtime; ca-certificates for HTTPS (Gemini, GitHub, OAuth).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Node 22 replaces the Node build the FalkorDB Browser ships with (the browser is not started).
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy
COPY --from=py /opt/python /opt/python
COPY --from=py /app/backend /app/backend
COPY --from=web /web /app/frontend
COPY data /app/data
COPY deploy/start.sh deploy/Caddyfile deploy/llm-cache.sqlite /app/deploy/

ENV FALKORDB_HOST=127.0.0.1 \
    FALKORDB_PORT=6379 \
    RELAY_GRAPH=cheerio \
    RELAY_TENANT=cheerio \
    RELAY_STEP_DELAY=0.5 \
    RELAY_COOKIE_SECURE=true \
    RELAY_DATA_DIR=/data \
    PORT=8080 \
    BROWSER=0 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/backend/.venv/bin:$PATH

# The base image ships /data as a symlink to /var/lib/falkordb/data; make it a plain directory so a
# Railway volume mounted at /data holds the state (start.sh creates /data/falkordb and /data/cache).
RUN rm -f /data && mkdir -p /data \
 && chmod +x /app/deploy/start.sh \
 && node --version && caddy version && relay --help >/dev/null \
 && caddy validate --config /app/deploy/Caddyfile --adapter caddyfile

WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["/app/deploy/start.sh"]
CMD []
