#!/bin/bash

# Function to show usage information
show_usage() {
    local script_name="${1:-$0}"
    echo "Usage: $script_name [OPTIONS] [COMMAND_ARGS...]"
    echo ""
    echo "Environment Options:"
    echo "  --local, -l          Use local environment (compose.local.yml)"
    echo "  --production, -p     Use production environment (compose.production.yml)"
    echo "  --env ENV            Specify environment explicitly (local|production)"
    echo "  --help, -h           Show this help message"
    echo ""
    echo "If no environment is specified, auto-detection will be used based on available .envs directories."
}

# Function to parse environment arguments and return remaining arguments
# Usage: parse_environment_args "$@"
# Returns: Sets CODA_ENV and populates remaining_args array with non-environment arguments
parse_environment_args() {
    local temp_env=""
    remaining_args=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --local|-l)
                temp_env="local"
                shift
                ;;
            --production|-p)
                temp_env="production"
                shift
                ;;
            --env)
                if [ -z "${2:-}" ]; then
                    echo "Error: --env requires a value." >&2
                    show_usage >&2
                    exit 1
                fi
                temp_env="$2"
                shift 2
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                # Non-environment argument, save it
                remaining_args+=("$1")
                shift
                ;;
        esac
    done

    # Set the environment
    CODA_ENV="$temp_env"
}

# Function to initialize the environment after parsing
init_environment() {
    # Skip if already initialized
    if [ -n "$COMPOSE_BASE_CMD" ]; then
        return 0
    fi

    # Auto-detect environment if not specified
    if [ -z "$CODA_ENV" ]; then
        if [ -d "$PWD/.envs/.local" ]; then
            CODA_ENV="local"
        elif [ -d "$PWD/.envs/.production" ]; then
            CODA_ENV="production"
        else
            echo "Error: Cannot determine environment. Please specify --local or --production, or ensure environment files exist."
            echo ""
            show_usage
            exit 1
        fi
    fi

    # Validate environment
    if [ "$CODA_ENV" != "local" ] && [ "$CODA_ENV" != "production" ]; then
        echo "Error: Environment must be 'local' or 'production'. Current value: $CODA_ENV"
        echo ""
        show_usage
        exit 1
    fi

    # Set up compose command based on environment
    if [ "$CODA_ENV" = "local" ]; then
        export COMPOSE_FILE="compose.local.yml"
        export ENV_DIR="$PWD/.envs/.local"
        export COMPOSE_BASE_CMD="docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/django.env --env-file $ENV_DIR/postgres.env"
    else
        export COMPOSE_FILE="compose.production.yml"
        export ENV_DIR="$PWD/.envs/.production"
        export COMPOSE_BASE_CMD="docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $ENV_DIR/postgres.env"
    fi

    echo "Using environment: $CODA_ENV (compose file: $COMPOSE_FILE)"
}

# Standalone execution: resolve and report the environment.
# When sourced (BASH_SOURCE != $0) this file only defines functions.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    parse_environment_args "$@"
    init_environment
fi
