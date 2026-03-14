#!/bin/bash
# One-time GCP setup for CityBus deployment.
# Usage: ./scripts/setup_gcp.sh [project-id]

set -e

PROJECT=${1:-$(gcloud config get-value project)}

echo "=== CityBus GCP Setup ==="
echo "Project: $PROJECT"
echo

# Enable required APIs
echo "Enabling Cloud Run API..."
gcloud services enable run.googleapis.com --project "$PROJECT"

echo "Enabling Container Registry..."
gcloud services enable artifactregistry.googleapis.com --project "$PROJECT"

echo "Enabling Compute Engine..."
gcloud services enable compute.googleapis.com --project "$PROJECT"

echo
echo "✓ GCP APIs enabled."
echo
echo "Next steps:"
echo "  1. Set up MongoDB Atlas: https://cloud.mongodb.com"
echo "  2. Set up Redis Cloud: https://redis.com/try-free"
echo "  3. Update .env with MONGO_URI and REDIS_URL"
echo "  4. Deploy API: ./scripts/deploy_cloudrun.sh"
echo "  5. Deploy Worker: ./scripts/deploy_worker_vm.sh <server_ip>"
