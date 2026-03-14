#!/bin/bash
# Deploy CityBus API + Bot to Google Cloud Run.
# Usage: ./scripts/deploy_cloudrun.sh [project-id] [region]

set -e

PROJECT=${1:-$(gcloud config get-value project)}
REGION=${2:-us-central1}
SERVICE="citybus-api"

echo "=== Deploying CityBus to Cloud Run ==="
echo "Project: $PROJECT"
echo "Region:  $REGION"
echo "Service: $SERVICE"
echo

# Build and deploy
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "$(cat .env | grep -v '^#' | grep -v '^$' | tr '\n' ',')" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5

echo
echo "✓ Deployed to Cloud Run"
echo "URL: $(gcloud run services describe $SERVICE --region $REGION --format 'value(status.url)')"
