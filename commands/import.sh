#!/bin/bash

# Import a local data file through a Django management command.
#
# Usage: import.sh [--local|--production] <manage-command> <file>

script_dir="$(cd "$(dirname "$0")" && pwd)"

# shellcheck source-path=SCRIPTDIR
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

usage() {
    echo "Usage: $0 [--local|--production] <manage-command> <file>" >&2
}

if [ ${#remaining_args[@]} -ne 2 ]; then
    usage
    exit 1
fi

# The first argument is passed to manage.py verbatim (e.g.
# import_invoices, import_fundingrequests) — new import commands need no
# change here. The regex only rejects paths/flags that can't be commands.
MANAGE_CMD="${remaining_args[0]}"
if ! [[ "$MANAGE_CMD" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "Error: first argument must be a manage.py command name, e.g. import_fundingrequests." >&2
    usage
    exit 1
fi

FILE_PATH="$(realpath "${remaining_args[1]}" 2>/dev/null)" || {
    echo "Error: file not found: ${remaining_args[1]}" >&2
    exit 1
}
MOUNT_DIR=$(dirname "$FILE_PATH")
FILE_NAME=$(basename "$FILE_PATH")

$COMPOSE_BASE_CMD run --rm -v "$MOUNT_DIR:/imports" django pdm run manage.py "$MANAGE_CMD" "/imports/$FILE_NAME"
