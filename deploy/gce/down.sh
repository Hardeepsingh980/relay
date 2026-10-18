#!/usr/bin/env bash
# Delete every GCP resource up.sh created for Relay.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
gc compute instances delete "$VM" --zone "$ZONE" --quiet || true
gc compute addresses delete "$IP_NAME" --region "$REGION" --quiet || true
gc compute firewall-rules delete relay-allow-web relay-allow-iap-ssh --quiet || true
gc compute networks subnets delete "$SUBNET" --region "$REGION" --quiet || true
gc compute networks delete "$NETWORK" --quiet || true
gc iam service-accounts delete "$SA_NAME@$PROJECT.iam.gserviceaccount.com" --quiet || true
echo "Relay resources removed from $PROJECT."
