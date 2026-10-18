#!/usr/bin/env bash
# Upload the current source to the VM and rebuild/restart the stack. Re-run after every change.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
ROOT="$(cd ../.. && pwd)"
IP=$(gc compute addresses describe "$IP_NAME" --region "$REGION" --format='value(address)')
DOMAIN="relay.${IP//./-}.sslip.io"

if [[ ! -f .env.prod ]]; then
  key=$(grep -E '^GEMINI_API_KEY=' "$ROOT/.env" | cut -d= -f2- || true)
  cat > .env.prod <<ENV
GEMINI_API_KEY=$key
RELAY_SECRET_KEY=$(openssl rand -hex 32)
RELAY_DOMAIN=$DOMAIN
RELAY_PUBLIC_URL=https://$DOMAIN
RELAY_API_PUBLIC_URL=https://$DOMAIN
RELAY_CORS_ORIGINS=https://$DOMAIN
RELAY_COOKIE_SECURE=true
RELAY_LLM_CACHE=build
RELAY_STEP_DELAY=0.5
RELAY_EVAL_EMAIL=judge@relay.app
RELAY_EVAL_PASSWORD=relay-graph-hacks
ENV
  chmod 600 .env.prod
fi

echo "== packing source"
TGZ="$(pwd)/relay-src.tgz"
(cd "$ROOT" && git ls-files -co --exclude-standard -z | grep -zv '^demo/' | tar --null -czf "$TGZ" -T - deploy/gce/.env.prod)
ls -lh "$TGZ" | awk '{print "   " $5}'

echo "== uploading"
gc compute scp "$TGZ" "$VM:/tmp/relay-src.tgz" --zone "$ZONE" --tunnel-through-iap --quiet
echo "== building and starting on the VM (a few minutes on first run)"
vm_ssh "set -e; sudo mkdir -p /opt/relay/app; cd /opt/relay/app; sudo tar -xzf /tmp/relay-src.tgz; \
  sudo chmod 600 deploy/gce/.env.prod; \
  sudo docker compose -f deploy/gce/compose.yml --env-file deploy/gce/.env.prod up -d --build; \
  sudo docker image prune -f >/dev/null"
echo "== waiting for https://$DOMAIN"
for i in $(seq 1 60); do
  if curl -fsS -o /dev/null "https://$DOMAIN/api/health"; then echo "== live: https://$DOMAIN"; exit 0; fi
  sleep 5
done
echo "Not answering yet. Logs: gcloud compute ssh $VM --zone $ZONE --tunnel-through-iap --command 'cd /opt/relay/app && sudo docker compose -f deploy/gce/compose.yml logs --tail 80'"
exit 1
