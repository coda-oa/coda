#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh "$@"

start_coda() {
	$COMPOSE_BASE_CMD up -d --build
}

start_coda
