#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <image-tag>"
  exit 1
fi

TAG="$1"
REGION="eu-central-1"

# Paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${PROJECT_ROOT}/infra"
SRC_DIR="${PROJECT_ROOT}/whiskybot"

# 1) Authenticate Docker to ECR
aws ecr get-login-password \
  --region "${REGION}" \
| docker login \
    --username AWS \
    --password-stdin "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${REGION}.amazonaws.com"

# 2) Read ECR URIs from Terraform
BACKEND_REPO="$(terraform -chdir="${INFRA_DIR}" output -raw backend_repo_url)"
UI_REPO="$(terraform -chdir="${INFRA_DIR}" output -raw ui_repo_url)"

# 3) Build & push backend
docker build \
  -f "${SRC_DIR}/Dockerfile" \
  -t "${BACKEND_REPO}:${TAG}" \
  "${SRC_DIR}"
docker push "${BACKEND_REPO}:${TAG}"

# 4) Build & push Chainlit UI
docker build \
  -f "${SRC_DIR}/Dockerfile.chainlit" \
  -t "${UI_REPO}:${TAG}" \
  "${SRC_DIR}"
docker push "${UI_REPO}:${TAG}"

echo "✅ Pushed backend → ${BACKEND_REPO}:${TAG}"
echo "✅ Pushed UI      → ${UI_REPO}:${TAG}"
