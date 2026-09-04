#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

stop_coda() {
	$COMPOSE_BASE_CMD down
}

stop_coda
