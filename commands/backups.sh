#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments using common.sh function
# shellcheck source-path=SCRIPTDIR
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

# Parse backup command from remaining arguments
if [[ ${#remaining_args[@]} -eq 0 ]]; then
    echo "Error: Please provide a backup command."
    echo "Usage: $0 [--local|--production] <create|list|restore> [backup_name]"
    exit 1
fi

BACKUP_CMD="${remaining_args[0]}"

# Build the postgres command as an array so subcommand and backup name
# reach the container as separate argv entries (a quoted single string
# would arrive as one argument, which the postgres entrypoint can't exec).
POSTGRES_CMD=()
if [[ "$BACKUP_CMD" == "create" ]]; then
    POSTGRES_CMD=(backup)
elif [[ "$BACKUP_CMD" == "list" ]]; then
    POSTGRES_CMD=(backups)
elif [[ "$BACKUP_CMD" == "restore" ]]; then
    if [[ ${#remaining_args[@]} -lt 2 ]]; then
        echo "Error: Please provide backup name for restore."
        echo "Usage: $0 [--local|--production] restore <backup_name>"
        exit 1
    fi
    echo "Shutting down CODA to restore backup..."
    $COMPOSE_BASE_CMD stop django
    echo "Ensuring postgres service is running for restore..."
    $COMPOSE_BASE_CMD up -d postgres
    POSTGRES_CMD=(restore "${remaining_args[1]}")
else
    echo "Invalid command $BACKUP_CMD"
    echo "Usage: $0 [--local|--production] <create|list|restore> [backup_name]"
    exit 1
fi

$COMPOSE_BASE_CMD run --rm postgres "${POSTGRES_CMD[@]}"
