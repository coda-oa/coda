#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments using common.sh function
# shellcheck source-path=SCRIPTDIR
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

echo "Running collation version check and fix for the '${CODA_ENV}' environment..."
echo ""

$COMPOSE_BASE_CMD run --rm postgres fix-collation
