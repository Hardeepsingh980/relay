# Shared settings for the Relay GCE deploy scripts.
PROJECT="${RELAY_GCP_PROJECT:-cheerio-app}"
REGION="${RELAY_GCP_REGION:-asia-south1}"
ZONE="${RELAY_GCP_ZONE:-asia-south1-a}"
VM="relay-vm"
NETWORK="relay-vpc"
SUBNET="relay-subnet"
IP_NAME="relay-ip"
SA_NAME="relay-vm"
LABELS="app=relay-hackathon"
gc() { gcloud --project "$PROJECT" "$@"; }
vm_ssh() { gcloud --project "$PROJECT" compute ssh "$VM" --zone "$ZONE" --tunnel-through-iap --quiet --command "$1"; }
