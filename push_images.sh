#!/usr/bin/env bash
set -euo pipefail

# Usage: ./push_images.sh [<image-tag>]
if [ $# -gt 1 ]; then
  echo "Usage: $0 [<image-tag>]"
  exit 1
fi

# Directories
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${PROJECT_ROOT}/infra"
TFVARS_FILE="${INFRA_DIR}/terraform.tfvars"
SRC_DIR="${PROJECT_ROOT}/whiskybot"
REGION="eu-central-1"

# Determine TAG: use argument if given; otherwise read & bump tfvars
if [ $# -eq 1 ]; then
  TAG="$1"
else
  # extract current tag from terraform.tfvars (line must exactly match image_tag = "vX.Y")
  current_tag=$(grep -E '^[[:space:]]*image_tag[[:space:]]*=[[:space:]]*"v[0-9]+\.[0-9]+"[[:space:]]*$' "${TFVARS_FILE}" \
                | sed -E 's/^[[:space:]]*image_tag[[:space:]]*=[[:space:]]*"([^\"]+)".*/\1/')
  if [[ "${current_tag}" =~ ^v([0-9]+\.[0-9]+)$ ]]; then
    num="${BASH_REMATCH[1]}"
    # add 0.01
    new_num=$(awk "BEGIN { printf \"%.2f\", ${num} + 0.01 }")
    # strip trailing zeros and optional trailing dot
    new_num=$(echo "${new_num}" | sed -E 's/0+$//' | sed -E 's/\.$//')
    TAG="v${new_num}"
  else
    echo "Warning: could not parse current tag '${current_tag}', defaulting to v0.1"
    TAG="v0.1"
  fi
fi

echo "Using image tag: ${TAG}"

# 1) Update terraform.tfvars (match only the exact image_tag entry)
sed -i -E 's/^[[:space:]]*image_tag[[:space:]]*=[[:space:]]*"v[0-9]+\.[0-9]+"[[:space:]]*$/image_tag = "'"${TAG}"'"/' "${TFVARS_FILE}"
echo "✅ Updated ${TFVARS_FILE}: image_tag = \"${TAG}\""

# 2) Authenticate Docker to ECR
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin \
    "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${REGION}.amazonaws.com"

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
