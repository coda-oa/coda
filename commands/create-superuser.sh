#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source-path=SCRIPTDIR
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

$COMPOSE_BASE_CMD exec django pdm run manage.py createsuperuser
