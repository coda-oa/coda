#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh

$COMPOSE_BASE_CMD down
