#!/usr/bin/env bash
# Entrypoint for the single Relay container.
#
#   Caddy :$PORT  -> /healthz (always 200), /api/* -> uvicorn 127.0.0.1:8020, else -> Next.js 127.0.0.1:3000
#   FalkorDB (redis-server + falkordb.so) on 127.0.0.1:6379, data in $RELAY_DATA_DIR/falkordb
#
# Order: Caddy and Next.js start first (so the healthcheck passes), then FalkorDB, then the graph
# builds for the tenants that have no graph yet, then the API. If any long-running process exits,
# the others are stopped and the container exits non-zero (Railway restarts it: ON_FAILURE).
set -euo pipefail

APP=/app
PORT="${PORT:-8080}"
DATA="${RELAY_DATA_DIR:-/data}"
REDIS_PORT="${FALKORDB_PORT:-6379}"
TENANTS="${RELAY_BUILD_TENANTS:-cheerio lumen}"

log() { printf '[relay-start] %s\n' "$*"; }

declare -A NAME=()  # pid -> process name

start_bg() {  # start_bg <name> <cmd...>
	local name=$1
	shift
	"$@" &
	NAME[$!]=$name
	log "started $name (pid $!)"
}

stop_all() {  # stop the app processes first, FalkorDB last (it saves its RDB on SIGTERM)
	local pid redis=""
	for pid in "${!NAME[@]}"; do
		if [[ ${NAME[$pid]} == falkordb ]]; then redis=$pid; else kill -TERM "$pid" 2>/dev/null || true; fi
	done
	for pid in "${!NAME[@]}"; do
		[[ $pid == "$redis" ]] || wait "$pid" 2>/dev/null || true
	done
	if [[ -n $redis ]]; then
		kill -TERM "$redis" 2>/dev/null || true
		wait "$redis" 2>/dev/null || true
	fi
}

on_signal() {
	trap - TERM INT
	log "signal received, shutting down"
	[[ -n ${JOB:-} ]] && kill -TERM "$JOB" 2>/dev/null || true
	stop_all
	exit 0
}
trap on_signal TERM INT

run() {  # run a foreground step as a child so signals are handled while it runs
	"$@" &
	JOB=$!
	local rc=0
	wait "$JOB" || rc=$?
	JOB=""
	return "$rc"
}

# ------------------------------------------------------------ persistent state
# $DATA is the Railway volume mount (ephemeral without one). REPO_ROOT/.cache holds the Gemini response
# cache, the generated secret key (when RELAY_SECRET_KEY is unset) and runtime job records.
mkdir -p "$DATA/falkordb" "$DATA/cache"
if [[ -L $APP/.cache || ! -e $APP/.cache ]]; then
	ln -sfn "$DATA/cache" "$APP/.cache"
fi
CACHE="$APP/.cache"
SEED_CACHE="$APP/deploy/llm-cache.sqlite"
if [[ ! -s $CACHE/llm.sqlite ]]; then
	cp "$SEED_CACHE" "$CACHE/llm.sqlite"
	log "seeded the Gemini response cache into $CACHE/llm.sqlite"
else
	# Keep answers cached on the volume and add any new ones shipped with this image.
	added=$(python -I -c '
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
c.execute("ATTACH DATABASE ? AS seed", (sys.argv[2],))
n = c.execute("INSERT OR IGNORE INTO cache SELECT key, value FROM seed.cache").rowcount
c.commit()
print(n)' "$CACHE/llm.sqlite" "$SEED_CACHE") && log "merged $added new cached Gemini answers from the image" \
		|| log "warning: could not merge the shipped Gemini cache; keeping the existing one"
fi
[[ -n ${RELAY_SECRET_KEY:-} ]] || log "warning: RELAY_SECRET_KEY is not set; using a generated key in $CACHE/secret.key"

# ------------------------------------------------------------ front door + web
start_bg caddy caddy run --config "$APP/deploy/Caddyfile" --adapter caddyfile
(cd "$APP/frontend" && exec node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000) &
NAME[$!]=web
log "started web (pid $!)"

# ------------------------------------------------------------ FalkorDB
start_bg falkordb redis-server \
	--bind 127.0.0.1 --port "$REDIS_PORT" --protected-mode yes \
	--dir "$DATA/falkordb" --dbfilename dump.rdb \
	--save 300 1 --appendonly no \
	--loadmodule /var/lib/falkordb/bin/falkordb.so \
	MAX_QUEUED_QUERIES 50 TIMEOUT 15000 RESULTSET_SIZE 20000

rcli() { redis-cli -h 127.0.0.1 -p "$REDIS_PORT" "$@"; }

for _ in $(seq 1 600); do  # up to 2 minutes (loading a large RDB answers -LOADING)
	[[ $(rcli PING 2>/dev/null || true) == PONG ]] && break
	for pid in "${!NAME[@]}"; do
		kill -0 "$pid" 2>/dev/null || { log "${NAME[$pid]} exited during startup"; stop_all; exit 1; }
	done
	sleep 0.2
done
[[ $(rcli PING 2>/dev/null || true) == PONG ]] || { log "FalkorDB did not answer PING"; stop_all; exit 1; }
log "FalkorDB is up"

# ------------------------------------------------------------ graph builds
# Gemini extraction by default (it replays the shipped response cache); the seed annotations when
# there is no API key, or when the Gemini build fails.
EXTRACTOR="${RELAY_EXTRACTOR:-gemini}"
if [[ $EXTRACTOR == gemini && -z ${GEMINI_API_KEY:-} ]]; then
	log "GEMINI_API_KEY is not set: building with the seed extractor"
	EXTRACTOR=seed
fi
export RELAY_EXTRACTOR="$EXTRACTOR"

has_graph() {
	local graphs
	graphs=$(rcli GRAPH.LIST 2>/dev/null || true)
	grep -qxF "$1" <<<"$graphs"
}

build_tenant() {
	local t=$1 started=$SECONDS
	if [[ ${RELAY_FORCE_BUILD:-0} != 1 ]] && has_graph "${t}_base"; then
		if has_graph "$t"; then
			log "graph ${t}_base exists, skipping the $t build"
		else
			log "graph ${t}_base exists, restoring the working graph $t from it"
			run relay --tenant "$t" reset || return 1
		fi
		return 0
	fi
	log "building the $t graph (extractor: $EXTRACTOR)"
	if ! run relay --tenant "$t" build --extractor "$EXTRACTOR"; then
		[[ $EXTRACTOR != seed ]] || { log "the $t build failed"; return 1; }
		log "the $t build failed with $EXTRACTOR, retrying with the seed extractor"
		run relay --tenant "$t" build --extractor seed || { log "the $t build failed"; return 1; }
	fi
	log "built the $t graph in $((SECONDS - started))s"
}

cd "$APP/backend"
for t in $TENANTS; do
	build_tenant "$t" || { stop_all; exit 1; }
done
rcli SAVE >/dev/null || true  # persist the fresh build right away

# ------------------------------------------------------------ API
start_bg api uvicorn relay.api:app \
	--host 127.0.0.1 --port 8020 \
	--proxy-headers --forwarded-allow-ips 127.0.0.1 \
	--timeout-graceful-shutdown 5

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

for _ in $(seq 1 300); do  # up to 60 s for the API and the web app to accept connections
	for pid in "${!NAME[@]}"; do
		kill -0 "$pid" 2>/dev/null || { log "${NAME[$pid]} exited during startup"; stop_all; exit 1; }
	done
	port_open 8020 && port_open 3000 && break
	sleep 0.2
done
if port_open 8020 && port_open 3000; then
	log "ready: Relay is listening on :$PORT"
else
	log "warning: the API or the web app is not accepting connections yet"
fi

# ------------------------------------------------------------ supervise
rc=0
EXITED=""
wait -n -p EXITED "${!NAME[@]}" || rc=$?
if [[ -n $EXITED ]]; then
	log "${NAME[$EXITED]} exited (code $rc); stopping the container"
	unset "NAME[$EXITED]"
else
	log "a process exited (code $rc); stopping the container"
fi
stop_all
exit $((rc == 0 ? 1 : rc))
