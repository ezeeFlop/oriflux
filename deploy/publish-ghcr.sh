#!/bin/bash

# Oriflux — publish the public self-host images to GHCR (issue #71).
#
# Builds multi-arch (linux/amd64 + linux/arm64) images and pushes:
#   ghcr.io/ezeeflop/oriflux-api       (migrations owner, REST + MCP)
#   ghcr.io/ezeeflop/oriflux-ingest    (same layers, ingest entrypoint)
#   ghcr.io/ezeeflop/oriflux-workers   (same layers, celery entrypoint)
#   ghcr.io/ezeeflop/oriflux-web       (nginx + SPA)
# each tagged :<version> (from api/pyproject.toml) and :latest.
#
# Usage:
#   ./publish-ghcr.sh [--no-push] [--no-cache] [--tag EXTra_TAG]
#
# Auth (never committed): docker login ghcr.io -u <user> with a classic PAT
# holding write:packages, or GITHUB_TOKEN in CI. Images must be marked
# "public" once in the GHCR package settings after the first push.
#
# Environment:
#   GHCR_NAMESPACE     default ghcr.io/ezeeflop
#   TARGET_PLATFORM    default linux/amd64,linux/arm64
#   BUILDX_BUILDER     default oriflux-multiarch

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

GHCR_NAMESPACE=${GHCR_NAMESPACE:-"ghcr.io/ezeeflop"}
TARGET_PLATFORM=${TARGET_PLATFORM:-"linux/amd64,linux/arm64"}
BUILDX_BUILDER=${BUILDX_BUILDER:-"oriflux-multiarch"}

DO_PUSH="true"; NO_CACHE=""; EXTRA_TAG=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        --no-push) DO_PUSH="false"; shift ;;
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        --tag) EXTRA_TAG="$2"; shift 2 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"
VERSION=$(grep -m1 '^version = ' "${REPO_ROOT}/api/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')

if ! docker buildx inspect "${BUILDX_BUILDER}" &>/dev/null; then
    docker buildx create --name "${BUILDX_BUILDER}" --driver docker-container --use
else
    docker buildx use "${BUILDX_BUILDER}"
fi

PUSH_FLAG="--push"
[ "${DO_PUSH}" = "false" ] && PUSH_FLAG=""

tags() {  # tags <image> → repeated -t flags (version + latest + optional extra)
    local image="${GHCR_NAMESPACE}/$1"
    echo -n "-t ${image}:${VERSION} -t ${image}:latest"
    [ -n "${EXTRA_TAG}" ] && echo -n " -t ${image}:${EXTRA_TAG}"
}

echo -e "${GREEN}Publishing Oriflux ${VERSION} to ${GHCR_NAMESPACE} (${TARGET_PLATFORM})${NC}"

echo -e "${CYAN}[1/4] oriflux-api${NC}"
# shellcheck disable=SC2046
docker buildx build --platform "${TARGET_PLATFORM}" ${NO_CACHE} ${PUSH_FLAG} \
    $(tags oriflux-api) "${REPO_ROOT}/api"

# ingest & workers share every layer of the api image — only CMD differs.
# They FROM the just-pushed api tag, so they only build on push runs.
if [ "${DO_PUSH}" = "true" ]; then
    echo -e "${CYAN}[2/4] oriflux-ingest${NC}"
    # shellcheck disable=SC2046
    printf 'FROM %s/oriflux-api:%s\nCMD ["uvicorn", "oriflux.ingest.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]\n' \
        "${GHCR_NAMESPACE}" "${VERSION}" | \
        docker buildx build --platform "${TARGET_PLATFORM}" ${PUSH_FLAG} \
            $(tags oriflux-ingest) -f - "${REPO_ROOT}/api"

    echo -e "${CYAN}[3/4] oriflux-workers${NC}"
    # shellcheck disable=SC2046
    printf 'FROM %s/oriflux-api:%s\nCMD ["bash", "workers-entrypoint.sh"]\n' \
        "${GHCR_NAMESPACE}" "${VERSION}" | \
        docker buildx build --platform "${TARGET_PLATFORM}" ${PUSH_FLAG} \
            $(tags oriflux-workers) -f - "${REPO_ROOT}/api"
else
    echo -e "${CYAN}[2-3/4] oriflux-ingest / oriflux-workers skipped (derive from the pushed api tag)${NC}"
fi

echo -e "${CYAN}[4/4] oriflux-web${NC}"
# shellcheck disable=SC2046
docker buildx build --platform "${TARGET_PLATFORM}" ${NO_CACHE} ${PUSH_FLAG} \
    --build-arg VITE_GOOGLE_CLIENT_ID="${VITE_GOOGLE_CLIENT_ID:-}" \
    $(tags oriflux-web) "${REPO_ROOT}/web"

echo -e "${GREEN}✓ published oriflux-{api,ingest,workers,web} ${VERSION} + latest${NC}"
[ "${DO_PUSH}" = "false" ] && echo "(build-only run: nothing pushed)"
