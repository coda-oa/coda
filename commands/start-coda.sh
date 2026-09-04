#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source-path=SCRIPTDIR
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

# echo owner/repo for GitHub URLs of any scheme (scp-style, ssh://, https://);
# nonzero for anything that doesn't parse, so _get_repo falls through.
_gh_repo() {
	local remote_url="$1"
	local repo_slug
	repo_slug=$(printf '%s' "$remote_url" | sed 's/.*github.com[:\/]//;s/\.git$//')
	[[ "$repo_slug" == */* && "$repo_slug" != *:* ]] || return 1
	echo "$repo_slug"
}

_get_repo() {
	local remote url
	remote=$(git rev-parse --abbrev-ref "@{upstream}" 2>/dev/null | cut -d/ -f1)
	if [[ -n "$remote" ]]; then
		url=$(git remote get-url "$remote" 2>/dev/null) && _gh_repo "$url" && return
	fi
	url=$(git remote get-url origin 2>/dev/null) && _gh_repo "$url" && return
	echo "coda-oa/coda"
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
