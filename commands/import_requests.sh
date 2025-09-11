#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh

MOUNT_DIR=$(dirname $1)
FILE_NAME=$(basename $1)

$COMPOSE_BASE_CMD run --rm -v $MOUNT_DIR:/imports django pdm run manage.py import_fundingrequests /imports/$FILE_NAME
