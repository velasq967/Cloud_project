#!/usr/bin/env bash
# Construye y publica las imágenes de la Fase 1 en Amazon ECR.
# Uso: ./scripts/aws/build-push.sh 123456789012 us-east-1 1.0.0
set -euo pipefail

ACCOUNT_ID="${1:?Uso: $0 <account_id> [region] [tag]}"
REGION="${2:-us-east-1}"
TAG="${3:-1.0.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

echo "==> Login a ECR"
aws ecr get-login-password --region "$REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"

echo "==> Build API"
docker build --platform linux/amd64 \
  -t "warehouse-api:$TAG" \
  -f "$ROOT/services/warehouse-api/Dockerfile" "$ROOT"
docker tag "warehouse-api:$TAG" "$REGISTRY/warehouse-api:$TAG"
docker push "$REGISTRY/warehouse-api:$TAG"

echo "==> Build Frontend"
docker build --platform linux/amd64 \
  -t "warehouse-frontend:$TAG" \
  -f "$ROOT/services/frontend/app/Dockerfile" "$ROOT"
docker tag "warehouse-frontend:$TAG" "$REGISTRY/warehouse-frontend:$TAG"
docker push "$REGISTRY/warehouse-frontend:$TAG"

echo
echo "Imágenes publicadas:"
echo "$REGISTRY/warehouse-api:$TAG"
echo "$REGISTRY/warehouse-frontend:$TAG"
