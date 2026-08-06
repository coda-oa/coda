#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh "$@"

_get_repo() {
	local remote
	remote=$(git rev-parse --abbrev-ref @{upstream} 2>/dev/null | cut -d/ -f1)
	if [[ -n "$remote" ]]; then
		git remote get-url "$remote" 2>/dev/null | sed 's/.*github.com[:\/]//' | sed 's/\.git$//' && return
	fi
	git remote get-url origin 2>/dev/null | sed 's/.*github.com[:\/]//' | sed 's/\.git$//' || echo "coda-oa/coda"
}

start_coda() {
	CODA_DESCRIBE=$(git describe --tags --exact-match 2>/dev/null || true)
	CODA_VERSION="${CODA_DESCRIBE:-$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")}"
	CODA_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
	CODA_REPO=$(_get_repo)
	CODA_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
	$COMPOSE_BASE_CMD build \
	  --build-arg GIT_COMMIT="$CODA_VERSION" \
	  --build-arg GIT_BRANCH="$CODA_BRANCH" \
	  --build-arg GIT_TAG="$CODA_DESCRIBE" \
	  --build-arg GIT_REPO="$CODA_REPO" \
	  --build-arg GIT_SHA="$CODA_SHA"
	$COMPOSE_BASE_CMD up -d
}

start_coda
