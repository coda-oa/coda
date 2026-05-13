#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

# Custom usage for update script
show_update_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Environment Options:"
    echo "  --local, -l          Use local environment (compose.local.yml)"
    echo "  --production, -p     Use production environment (compose.production.yml)"
    echo "  --env ENV            Specify environment explicitly (local|production)"
    echo ""
    echo "Update Options:"
    echo "  --branch BRANCH      Git branch to pull from (default: stable)"
    echo "  --backup             Create backup before updating"
    echo "  --no-backup          Skip backup creation (default)"
    echo "  --help, -h           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --production --backup"
    echo "  $0 --local --branch develop"
    echo "  $0 --production --backup --branch stable"

    return 0
}

# Parse update-specific arguments
parse_update_args() {
    BRANCH="stable"
    CREATE_BACKUP=false

    while [[ $# -gt 0 ]]; do
        local arg="$1"
        case "$arg" in
            --branch)
                BRANCH="$2"
                shift 2
                ;;
            --backup)
                CREATE_BACKUP=true
                shift
                ;;
            --no-backup)
                CREATE_BACKUP=false
                shift
                ;;
            --help|-h)
                show_update_usage
                exit 0
                ;;
            *)
                # Pass to common.sh for environment parsing
                shift
                ;;
        esac
    done

    return 0
}

# Parse arguments before sourcing common.sh
parse_update_args "$@"

# Source common.sh for environment setup
source ${script_dir}/common.sh "$@"

update_coda() {
    echo "CODA Update Script"
    echo "Environment: $CODA_ENV"
    echo "Branch: $BRANCH"
    echo "Backup: $([[ "$CREATE_BACKUP" == true ]] && echo "Yes" || echo "No")"
    echo ""

    # Step 1: Create backup if requested
    if [[ "$CREATE_BACKUP" == true ]]; then
        echo "Step 1/4: Creating backup..."
        ${script_dir}/backups.sh --${CODA_ENV} create
        if [[ $? -ne 0 ]]; then
            echo "Error: Backup failed. Aborting update." >&2
            exit 1
        fi
        echo ""
    else
        echo "Step 1/4: Skipping backup (use --backup to create one)"
        echo ""
    fi

    # Step 2: Stop CODA
    echo "Step 2/4: Stopping CODA..."
    ${script_dir}/stop-coda.sh --${CODA_ENV}
    if [[ $? -ne 0 ]]; then
        echo "Error: Failed to stop CODA. Aborting update." >&2
        exit 1
    fi
    echo ""

    # Step 3: Pull latest changes
    echo "Step 3/4: Pulling latest changes from branch '$BRANCH'..."
    git pull origin $BRANCH
    if [[ $? -ne 0 ]]; then
        echo "Error: Git pull failed. Starting CODA with current version..." >&2
        ${script_dir}/start-coda.sh --${CODA_ENV}
        exit 1
    fi
    echo ""

    # Step 4: Start CODA
    echo "Step 4/4: Starting CODA (this will rebuild containers and run migrations)..."
    ${script_dir}/start-coda.sh --${CODA_ENV}
    if [[ $? -ne 0 ]]; then
        echo "Error: Failed to start CODA." >&2
        exit 1
    fi
    echo ""

    echo "Update completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Verify CODA is accessible in your web browser"
    echo "2. Check that you can log in successfully"
    echo "3. Verify that your data is intact"
    echo ""
    if [[ "$CREATE_BACKUP" == true ]]; then
        echo "Note: A backup was created before the update."
        echo "You can list backups with: ./commands/backups.sh --${CODA_ENV} list"
        echo ""
    fi

    return 0
}

update_coda
