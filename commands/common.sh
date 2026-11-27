#!/bin/bash

# Function to show the environment options shared by every command script
show_environment_options() {
    echo "Environment Options:"
    echo "  --production, -p     Use production environment (compose.production.yml) [default]"
    echo "  --local, -l          Use local environment (compose.local.yml)"
    echo "  --env ENV            Specify environment explicitly (local|production)"
    echo "  --help, -h           Show this help message"
    return 0
}

# Function to show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND_ARGS...]"
    echo ""
    show_environment_options
    echo ""
    echo "Default environment: production (compose.production.yml). Use --local for the local dev stack."
    return 0
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
                if [[ -z "${2:-}" ]]; then
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
            -*)
                # A flag no script consumed: typo or a flag this script does
                # not know. Silently ignoring it would fall through to the
                # default environment, i.e. run against production.
                echo "Error: unknown option '$1'." >&2
                show_usage >&2
                exit 1
                ;;
            *)
                # Non-environment argument, save it
                remaining_args+=("$1")
                shift
                ;;
        esac
    done

    # Production is the default; the local dev stack must be requested.
    CODA_ENV="${temp_env:-production}"
}

# Function to initialize the environment after parsing
init_environment() {
    if [[ -n "${COMPOSE_BASE_CMD:-}" ]]; then
        return 0
    fi

    # Validate environment
    if [[ "$CODA_ENV" != "local" && "$CODA_ENV" != "production" ]]; then
        echo "Error: Environment must be 'local' or 'production'. Current value: $CODA_ENV"
        echo ""
        show_usage
        exit 1
    fi

    # Set up compose command based on environment
    if [[ "$CODA_ENV" == "local" ]]; then
        export COMPOSE_FILE="compose.local.yml"
        export ENV_DIR="$PWD/.envs/.local"
    else
        export COMPOSE_FILE="compose.production.yml"
        export ENV_DIR="$PWD/.envs/.production"
    fi

    if [[ ! -d "$ENV_DIR" ]]; then
        echo "Error: $ENV_DIR not found. Create it or select another environment with --local / --production." >&2
        exit 1
    fi

    if [[ "$CODA_ENV" == "local" ]]; then
        export COMPOSE_BASE_CMD="docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/django.env --env-file $ENV_DIR/postgres.env"
    else
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
