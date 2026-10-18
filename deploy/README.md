# Deploying Relay (one container)

Relay runs as one Docker container. The target is Railway (linux/amd64), but any Docker host works.

```
            Railway edge (TLS)
                   |
             :$PORT  Caddy ── /healthz ──────────> 200 "ok"
                   ├──────── /api/* ─────────────> uvicorn relay.api:app   127.0.0.1:8020  (SSE flushed at once)
                   └──────── everything else ────> next start              127.0.0.1:3000
                                                      |
                              FalkorDB (redis-server + falkordb.so)  127.0.0.1:6379
                              data: /data/falkordb   cache: /app/.cache -> /data/cache
```

The browser calls the API on the same origin (`/api/...`). The web app is built with `NEXT_PUBLIC_RELAY_API=""` for this reason.

## Files

| File | Purpose |
| --- | --- |
| `deploy/Dockerfile` | Multi-stage build. Stages: web (pnpm, `next build`), py (uv, Python 3.12, `uv sync --frozen --no-dev`), runtime (`falkordb/falkordb:6.0.2` + Node 22 + Caddy + git). |
| `deploy/start.sh` | Entrypoint. Starts Caddy and Next.js, then FalkorDB, then builds missing graphs, then starts the API. It supervises all of them. |
| `deploy/Caddyfile` | Routes `/healthz`, `/api/*` and the web app. No TLS. gzip/zstd for everything except SSE. |
| `deploy/railway.json` | Railway config: Dockerfile builder, healthcheck `/healthz`, restart `ON_FAILURE`. |
| `deploy/llm-cache.sqlite` | Copy of the Gemini response cache (`.cache/llm.sqlite`). Graph builds replay it, so they do not call Gemini again. |
| `deploy/.gitignore` | Un-ignores `llm-cache.sqlite` (the root `.gitignore` drops `*.sqlite`). |
| `.dockerignore` (repo root) | Keeps `.env`, `.git`, `node_modules`, `.next`, `.venv` and `demo/` out of the build context. |

The repo-root `.env` holds secrets. It is never copied into the image.

## What happens at start

1. `/data/falkordb` and `/data/cache` are created. `/app/.cache` (the backend's `REPO_ROOT/.cache`) becomes a symlink to `/data/cache`.
2. The Gemini cache is copied to `/data/cache/llm.sqlite` on the first start. On later starts, answers that are new in the image are merged into it.
3. Caddy starts on `$PORT` (default 8080). `/healthz` answers 200 from this moment. Next.js starts on 127.0.0.1:3000.
4. FalkorDB starts on 127.0.0.1:6379 with `--save 300 1 --appendonly no` and the module arguments `MAX_QUEUED_QUERIES 50 TIMEOUT 15000 RESULTSET_SIZE 20000`.
5. For each tenant (`cheerio`, `lumen`): if `GRAPH.LIST` has no `<tenant>_base`, `relay --tenant <tenant> build` runs. If the base graph exists but the working graph does not, `relay --tenant <tenant> reset` restores it.
   - The extractor is `gemini` when `GEMINI_API_KEY` is set. It replays the cached answers. Without a key, the extractor is `seed`. If a Gemini build fails, the build runs again with `seed`.
6. uvicorn starts on 127.0.0.1:8020. Until then, `/api/*` returns 502.
7. If any process stops, the script stops the others and exits with a non-zero code. Railway then restarts the container.

Readiness: `GET /api/health` returns 200 only after the API is up. `/healthz` checks only that Caddy is up. This lets the Railway healthcheck pass while the graphs build.

Measured locally (arm64, Docker Desktop, October 2026):

- Image size: 1.42 GB. The `falkordb/falkordb:6.0.2` base is 0.5 GB of this. The Next.js `node_modules` is about 0.5 GB, because the app is not built with `output: "standalone"`.
- Cold build of the image: about 4 minutes.
- Cold start with an empty `/data`: about 4 to 5 seconds until the API is ready. Each graph build takes 1 to 3 seconds, with the seed extractor and with the Gemini extractor. All 780 (cheerio) and 791 (lumen) Gemini calls hit the shipped cache, so a build with a key makes no Gemini calls. This was tested with `--network none`.
- Warm start (graphs already in `/data`): about 2 seconds.

## Railway setup

1. Create a service from this repo (GitHub), or run `railway up` from the repo root. `railway up` uploads only files that `.gitignore` does not ignore. This is why the cache ships as `deploy/llm-cache.sqlite`, and not as `.cache/llm.sqlite`.
2. Tell Railway where the config is. Railway reads `railway.json` or `railway.toml` from the repo root by default. This config is at `deploy/railway.json`, so do one of these:
   - In the service settings, set **Railway Config File** to `/deploy/railway.json`. The path is absolute from the repo root. It does not follow the Root Directory setting.
   - Or set the service variable `RAILWAY_DOCKERFILE_PATH=deploy/Dockerfile`, and set the healthcheck path (`/healthz`) and the restart policy in the dashboard.
   - Note: Railway marks config-as-code files as deprecated. Existing files keep working for legacy services until 2026-12-01. After that, use the dashboard settings above (or Railway's Infrastructure as Code).
3. Leave the Root Directory empty. The Docker build context must be the repo root.
4. Add a **volume** mounted at `/data`. (The FalkorDB base image ships `/data` as a symlink to `/var/lib/falkordb/data`. The Dockerfile replaces it with a plain directory, so the volume holds the state.) It keeps the FalkorDB RDB (users, workspaces, graphs), the Gemini cache, the generated secret key and runtime job records (`.cache/repos/*.json`). Without a volume, each deploy starts empty: all graphs build again and all accounts are lost.
5. Keep **one replica**. FalkorDB runs inside the container, so replicas do not share data.
6. Generate a public domain. Then set the variables below.

### Variables

Set these in Railway (they are not in the image):

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `RELAY_SECRET_KEY` | yes | output of `openssl rand -base64 48` | Encrypts stored connection credentials. If it is not set, a key is generated in `/data/cache/secret.key`. Credentials then become unreadable when that file is lost. |
| `RELAY_PUBLIC_URL` | yes | `https://relay.up.railway.app` | Where the web app runs (invite links). |
| `RELAY_API_PUBLIC_URL` | yes | `https://relay.up.railway.app` | Same origin as the web app. The Google OAuth redirect is `<this>/api/auth/google/callback`. |
| `RELAY_CORS_ORIGINS` | recommended | `https://relay.up.railway.app` | Comma-separated. The browser uses the same origin, so this matters only for other origins. |
| `GEMINI_API_KEY` | optional | | Enables Gemini extraction (from the cache) and the live LLM features. Without it, builds use the seed extractor. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | optional | | Google sign-in and Google connections. |
| `JIRA_*`, `SLACK_WEBHOOK_URL`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID` | optional | | Live integrations (see `.env.example`). |
| `PORT` | set by Railway | `8080` | Caddy listens here. |

Defaults set in the image (override them as Railway variables when needed):

| Variable | Default | Notes |
| --- | --- | --- |
| `FALKORDB_HOST` / `FALKORDB_PORT` | `127.0.0.1` / `6379` | The in-container FalkorDB. |
| `RELAY_GRAPH` / `RELAY_TENANT` | `cheerio` / `cheerio` | Working graph and default tenant. |
| `RELAY_STEP_DELAY` | `0.5` | Demo pacing between investigation steps. |
| `RELAY_COOKIE_SECURE` | `true` | Set `false` only for plain-HTTP testing. |
| `RELAY_DATA_DIR` | `/data` | Mount the volume here. |
| `RELAY_EXTRACTOR` | (start.sh: `gemini`) | Set `seed` to always build from the seed annotations. |
| `RELAY_FORCE_BUILD` | unset | Set `1` to rebuild both graphs at the next start, even if they exist. Remove it afterwards. |
| `RELAY_BUILD_TENANTS` | `cheerio lumen` | Tenants built at start. |

## Build and test locally

From the repo root:

```bash
docker build -f deploy/Dockerfile -t relay-local .
docker run --rm -d -p 8088:8080 -e PORT=8080 \
  -e RELAY_COOKIE_SECURE=false \
  -e RELAY_PUBLIC_URL=http://localhost:8088 \
  -e RELAY_API_PUBLIC_URL=http://localhost:8088 \
  -e RELAY_CORS_ORIGINS=http://localhost:8088 \
  --name relay-local relay-local
docker logs -f relay-local          # wait for "ready: Relay is listening"
curl -s localhost:8088/healthz      # ok
curl -s localhost:8088/api/health   # API + FalkorDB
curl -s localhost:8088/api/auth/providers
```

Add `-v relay-data:/data` to keep state between runs. On an Apple Silicon Mac, the image builds for arm64. Railway builds it for amd64 on its own builders. To build amd64 locally, add `--platform linux/amd64` (slow under emulation).

## Maintenance

- The cache hits depend on the exact prompts and data. If the extraction code or `data/` changes, rebuild the cache locally (`relay build --extractor gemini` with a key), then refresh the shipped copy. Otherwise a build with a key calls Gemini for the missing answers.
- Refresh the shipped Gemini cache after new extractions:
  `sqlite3 .cache/llm.sqlite ".backup deploy/llm-cache.sqlite"`. On the next start, new answers are merged into the volume copy.
- Rebuild the graphs on Railway: set `RELAY_FORCE_BUILD=1`, redeploy, then remove the variable. Or delete the volume.
- Logs from all processes go to stdout. Lines from the entrypoint start with `[relay-start]`.
