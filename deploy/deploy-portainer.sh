#!/bin/bash

# Oriflux — Portainer deployment script (pattern: cliphaven/neokanban).
# Builds the single multi-arch api image (3 entrypoints), pushes it to the
# registry, and triggers the Portainer stack webhook for redeploy.
#
# Usage:
#   ./deploy-portainer.sh [options]
#
# Options:
#   --no-push     Build only (validation), skip push and deploy
#   --no-deploy   Push but don't trigger the Portainer webhook
#   --no-cache    Build without Docker cache
#   --tag TAG     Image tag (default: latest)
#   --help        Show this help
#
# Environment:
#   REGISTRY           registry URL       (default: registry.sponge-theory.dev)
#   TARGET_PLATFORM    build platforms    (default: linux/amd64,linux/arm64 —
#                      x86 nodes + the DGX Spark arm64 node)
#   BUILDX_BUILDER     buildx builder     (default: oriflux-multiarch)
#   PORTAINER_WEBHOOK  stack webhook URL — required to deploy. Never committed
#                      (public repo): export it, or put it in deploy/.env
#                      (gitignored), which this script sources if present.

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

REGISTRY=${REGISTRY:-"registry.sponge-theory.dev"}
TARGET_PLATFORM=${TARGET_PLATFORM:-"linux/amd64,linux/arm64"}
BUILDX_BUILDER=${BUILDX_BUILDER:-"oriflux-multiarch"}
# Load local, gitignored overrides (PORTAINER_WEBHOOK lives there, never in git).
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env"
[ -f "${ENV_FILE}" ] && . "${ENV_FILE}"
PORTAINER_WEBHOOK=${PORTAINER_WEBHOOK:-}
VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID:-"1031899381936-8g3t4qvikt248nfe76lm5kmcs39ahesq.apps.googleusercontent.com"}
MAX_RETRIES=${MAX_RETRIES:-5}

DO_PUSH="true"; DO_DEPLOY="true"; NO_CACHE=""; TAG=${TAG:-"latest"}

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        --no-push) DO_PUSH="false"; shift ;;
        --no-deploy) DO_DEPLOY="false"; shift ;;
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        --tag) TAG="$2"; shift 2 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"
API_DIR="${REPO_ROOT}/api"

if [ ! -f "${API_DIR}/Dockerfile" ]; then
    echo -e "${RED}Error: ${API_DIR}/Dockerfile not found${NC}"
    exit 1
fi

APP_VERSION=$(grep -m1 '^version = ' "${API_DIR}/pyproject.toml" | sed 's/version = "\(.*\)"/\1/' 2>/dev/null || echo "0.1.0")
GIT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
IMAGE="${REGISTRY}/oriflux-api"

echo -e "${GREEN}Oriflux — Portainer deployment${NC}"
echo "  Registry:  ${REGISTRY}"
echo "  Image:     ${IMAGE}:${TAG} (+ :${APP_VERSION})"
echo "  Platforms: ${TARGET_PLATFORM}"
echo "  Commit:    ${GIT_COMMIT}"
echo "  Push: ${DO_PUSH} | Deploy: ${DO_DEPLOY}"
echo ""

# Multi-arch builds require buildx and must be pushed directly to the
# registry — they cannot be loaded into the local image store.
if ! docker buildx inspect "${BUILDX_BUILDER}" &>/dev/null; then
    echo "Creating buildx builder '${BUILDX_BUILDER}'..."
    docker buildx create --name "${BUILDX_BUILDER}" --driver docker-container --use
else
    docker buildx use "${BUILDX_BUILDER}"
fi

WEB_IMAGE="${REGISTRY}/oriflux-web"
WEB_DIR="${REPO_ROOT}/web"
LANDING_IMAGE="${REGISTRY}/oriflux-landing"
LANDING_DIR="${REPO_ROOT}/landing"

if [ "${DO_PUSH}" = "true" ]; then
    echo -e "${CYAN}Building + pushing ${IMAGE} for ${TARGET_PLATFORM}...${NC}"
    attempt=1; delay=10
    until docker buildx build \
            --platform "${TARGET_PLATFORM}" \
            ${NO_CACHE} \
            --push \
            -f "${API_DIR}/Dockerfile" \
            -t "${IMAGE}:${TAG}" \
            -t "${IMAGE}:${APP_VERSION}" \
            "${API_DIR}"; do
        if [ ${attempt} -ge ${MAX_RETRIES} ]; then
            echo -e "${RED}✗ build/push failed after ${MAX_RETRIES} attempts${NC}"; exit 1
        fi
        attempt=$((attempt + 1))
        echo -e "${YELLOW}⚠ build/push failed, retrying in ${delay}s (attempt ${attempt}/${MAX_RETRIES})${NC}"
        sleep ${delay}; delay=$(( delay * 2 > 60 ? 60 : delay * 2 ))
    done
    echo -e "${GREEN}✓ pushed ${IMAGE}:${TAG}${NC}"

    echo -e "${CYAN}Building + pushing ${WEB_IMAGE} for ${TARGET_PLATFORM}...${NC}"
    docker buildx build \
        --platform "${TARGET_PLATFORM}" \
        ${NO_CACHE} \
        --push \
        --build-arg VITE_GOOGLE_CLIENT_ID="${VITE_GOOGLE_CLIENT_ID:-}" \
        -f "${WEB_DIR}/Dockerfile" \
        -t "${WEB_IMAGE}:${TAG}" \
        -t "${WEB_IMAGE}:${APP_VERSION}" \
        "${REPO_ROOT}"
    echo -e "${GREEN}✓ pushed ${WEB_IMAGE}:${TAG}${NC}"

    echo -e "${CYAN}Building + pushing ${LANDING_IMAGE} for ${TARGET_PLATFORM}...${NC}"
    docker buildx build \
        --platform "${TARGET_PLATFORM}" \
        ${NO_CACHE} \
        --push \
        --build-arg PUBLIC_LIVE_DEMO_URL="${PUBLIC_LIVE_DEMO_URL:-}" \
        -f "${LANDING_DIR}/Dockerfile" \
        -t "${LANDING_IMAGE}:${TAG}" \
        -t "${LANDING_IMAGE}:${APP_VERSION}" \
        "${REPO_ROOT}"
    echo -e "${GREEN}✓ pushed ${LANDING_IMAGE}:${TAG}${NC}"
else
    echo -e "${CYAN}Building ${IMAGE} for ${TARGET_PLATFORM} (no push)...${NC}"
    docker buildx build \
        --platform "${TARGET_PLATFORM}" \
        ${NO_CACHE} \
        -f "${API_DIR}/Dockerfile" \
        -t "oriflux-api:${APP_VERSION}" \
        "${API_DIR}"
    echo -e "${GREEN}✓ build validated${NC}"
fi

if [ "${DO_PUSH}" = "true" ] && [ "${DO_DEPLOY}" = "true" ]; then
    if [ -n "${PORTAINER_WEBHOOK}" ]; then
        echo "Triggering Portainer webhook..."
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${PORTAINER_WEBHOOK}")
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
            echo -e "${GREEN}✓ Portainer redeploy triggered (HTTP ${HTTP_CODE})${NC}"
        else
            echo -e "${RED}⚠ Portainer webhook returned HTTP ${HTTP_CODE}${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ PORTAINER_WEBHOOK not set — image pushed, redeploy manually in Portainer${NC}"
        echo "  (create the stack once from deploy/docker-stack.yml, then copy its webhook URL)"
    fi
fi

# Release annotation (issue #25): mark the deploy on the Oriflux timeline.
# Opt-in: set ORIFLUX_ANNOTATE_KEY (an ingest key of the project) and
# ORIFLUX_ANNOTATE_PROJECT (the project id). Failure never fails the deploy.
if [ -n "${ORIFLUX_ANNOTATE_KEY:-}" ] && [ -n "${ORIFLUX_ANNOTATE_PROJECT:-}" ]; then
    SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    curl -s -m 10 -o /dev/null -X POST \
        "${ORIFLUX_ANNOTATE_URL:-https://api.oriflux.sponge-theory.dev}/api/v1/projects/${ORIFLUX_ANNOTATE_PROJECT}/annotations" \
        -H "Authorization: Bearer ${ORIFLUX_ANNOTATE_KEY}" -H "Content-Type: application/json" \
        -d "{\"kind\":\"release\",\"text\":\"deploy ${SHA}\",\"happened_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
        && echo -e "${GREEN}✓ release annotation posted (${SHA})${NC}" || true
fi

echo -e "${GREEN}Done.${NC}"
