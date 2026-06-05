#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh "$@"

start_coda() {
	CODA_VERSION=$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "unknown")
	$COMPOSE_BASE_CMD --build-arg GIT_COMMIT="$CODA_VERSION" up -d --build
}

start_coda
