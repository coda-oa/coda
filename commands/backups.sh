#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments using common.sh function
source ${script_dir}/common.sh
parse_environment_args "$@"
init_environment

# Parse backup command from remaining arguments
if [ ${#remaining_args[@]} -eq 0 ]; then
    echo "Error: Please provide a backup command."
    echo "Usage: $0 [--local|--production] <create|list|restore> [backup_name]"
    exit 1
fi

BACKUP_CMD="${remaining_args[0]}"

if [[ $BACKUP_CMD = "create" ]]; then
    cmd="backup"
elif [[ $BACKUP_CMD = "list" ]]; then
    cmd="backups"
elif [[ $BACKUP_CMD = "restore" ]]; then
    if [ ${#remaining_args[@]} -lt 2 ]; then
        echo "Error: Please provide backup name for restore."
        echo "Usage: $0 [--local|--production] restore <backup_name>"
        exit 1
    fi
    echo "Shutting down CODA to restore backup..."
    $COMPOSE_BASE_CMD stop django
    echo "Ensuring postgres service is running for restore..."
    $COMPOSE_BASE_CMD up -d postgres
    cmd="restore ${remaining_args[1]}"
else
    echo "Invalid command $BACKUP_CMD"
    echo "Usage: $0 [--local|--production] <create|list|restore> [backup_name]"
    exit 1
fi

$COMPOSE_BASE_CMD run --rm -it postgres $cmd
