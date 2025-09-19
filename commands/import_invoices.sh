#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments using common.sh function
source ${script_dir}/common.sh
parse_environment_args "$@"
init_environment

# Check if file argument was provided
if [ ${#remaining_args[@]} -eq 0 ]; then
    echo "Error: Please provide a file path to import."
    echo "Usage: $0 [--local|--production] <file_path>"
    exit 1
fi

FILE_PATH="${remaining_args[0]}"
MOUNT_DIR=$(dirname "$FILE_PATH")
FILE_NAME=$(basename "$FILE_PATH")

$COMPOSE_BASE_CMD run --rm -v "$MOUNT_DIR:/imports" django pdm run manage.py import_invoices "/imports/$FILE_NAME"
