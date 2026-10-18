#!/usr/bin/env bash
# Create the isolated GCP resources for Relay (all named relay-*, labelled app=relay-hackathon), then deploy.
# Safe to re-run: existing resources are kept.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

exists() { "$@" >/dev/null 2>&1; }

echo "== project $PROJECT, zone $ZONE"
gc services enable compute.googleapis.com iap.googleapis.com >/dev/null

exists gc compute networks describe "$NETWORK" ||
  gc compute networks create "$NETWORK" --subnet-mode=custom
exists gc compute networks subnets describe "$SUBNET" --region "$REGION" ||
  gc compute networks subnets create "$SUBNET" --network "$NETWORK" --region "$REGION" --range 10.42.0.0/24
exists gc compute firewall-rules describe relay-allow-web ||
  gc compute firewall-rules create relay-allow-web --network "$NETWORK" --allow tcp:80,tcp:443 \
    --source-ranges 0.0.0.0/0 --target-tags relay-web
exists gc compute firewall-rules describe relay-allow-iap-ssh ||
  gc compute firewall-rules create relay-allow-iap-ssh --network "$NETWORK" --allow tcp:22 \
    --source-ranges 35.235.240.0/20 --target-tags relay-web
exists gc compute addresses describe "$IP_NAME" --region "$REGION" ||
  gc compute addresses create "$IP_NAME" --region "$REGION"
IP=$(gc compute addresses describe "$IP_NAME" --region "$REGION" --format='value(address)')
SA="$SA_NAME@$PROJECT.iam.gserviceaccount.com"
exists gc iam service-accounts describe "$SA" ||
  gc iam service-accounts create "$SA_NAME" --display-name "Relay VM (hackathon)"

if ! exists gc compute instances describe "$VM" --zone "$ZONE"; then
  gc compute instances create "$VM" --zone "$ZONE" --machine-type e2-standard-2 \
    --network "$NETWORK" --subnet "$SUBNET" --address "$IP" --tags relay-web \
    --service-account "$SA" --scopes logging-write,monitoring-write \
    --image-family debian-12 --image-project debian-cloud --boot-disk-size 40GB \
    --labels "$LABELS" \
    --metadata startup-script='#!/bin/bash
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
mkdir -p /opt/relay'
  echo "== waiting for the VM to install Docker"
  for i in $(seq 1 40); do
    if vm_ssh "command -v docker >/dev/null && sudo docker info >/dev/null 2>&1" 2>/dev/null; then break; fi
    sleep 10
  done
fi
echo "== VM ready at $IP"
./push.sh
