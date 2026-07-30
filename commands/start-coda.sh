#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh "$@"

start_coda() {
	CODA_VERSION=$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "unknown")
	CODA_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
	CODA_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "")
	$COMPOSE_BASE_CMD \
	  --build-arg GIT_COMMIT="$CODA_VERSION" \
	  --build-arg GIT_BRANCH="$CODA_BRANCH" \
	  --build-arg GIT_TAG="$CODA_TAG" \
	  up -d --build
}

start_coda
