#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh "$@"

stop_coda() {
	$COMPOSE_BASE_CMD down
}

stop_coda
