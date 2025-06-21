#!/usr/bin/env bash
set -euo pipefail

# Default tag if none provided
DEFAULT_TAG="v0.1"

if [ $# -gt 1 ]; then
  echo "Usage: $0 [<image-tag>]"
  exit 1
fi

if [ $# -eq 1 ]; then
  TAG="$1"
else
  TAG="$DEFAULT_TAG"
fi

REGION="eu-central-1"

# Paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${PROJECT_ROOT}/infra"
TFVARS_FILE="${INFRA_DIR}/terraform.tfvars"
SRC_DIR="${PROJECT_ROOT}/whiskybot"

# 1) Update terraform.tfvars with this TAG
#    Replace the line that sets image_tag to use the new value
if grep -q '^image_tag' "${TFVARS_FILE}"; then
  sed -i -E 's#^image_tag\s*=.*#image_tag = "'"${TAG}"'"#' "${TFVARS_FILE}"
else
  # if for some reason it wasn't there, append it
  echo "image_tag = \"${TAG}\"" >> "${TFVARS_FILE}"
fi
echo "✅ Updated ${TFVARS_FILE} → image_tag = \"${TAG}\""

# 2) Authenticate Docker to ECR
aws ecr get-login-password \
  --region "${REGION}" \
| docker login \
    --username AWS \
    --password-stdin "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${REGION}.amazonaws.com"

# 3) Read ECR URIs from Terraform
BACKEND_REPO="$(terraform -chdir="${INFRA_DIR}" output -raw backend_repo_url)"
UI_REPO="$(terraform -chdir="${INFRA_DIR}" output -raw ui_repo_url)"

# 4) Build & push backend
docker build \
  -f "${SRC_DIR}/Dockerfile" \
  -t "${BACKEND_REPO}:${TAG}" \
  "${SRC_DIR}"
docker push "${BACKEND_REPO}:${TAG}"

# 5) Build & push Chainlit UI
docker build \
  -f "${SRC_DIR}/Dockerfile.chainlit" \
  -t "${UI_REPO}:${TAG}" \
  "${SRC_DIR}"
docker push "${UI_REPO}:${TAG}"

echo "✅ Pushed backend → ${BACKEND_REPO}:${TAG}"
echo "✅ Pushed UI      → ${UI_REPO}:${TAG}"
