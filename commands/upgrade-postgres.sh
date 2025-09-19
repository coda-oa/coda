#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments using common.sh function, but handle postgres-version specially
source ${script_dir}/common.sh

postgres_version=""
filtered_args=()

# First pass: extract --postgres-version and filter other args
while [[ $# -gt 0 ]]; do
    case $1 in
        --postgres-version)
            postgres_version="$2"
            shift 2
            ;;
        *)
            filtered_args+=("$1")
            shift
            ;;
    esac
done

# Use common.sh functions for environment parsing
parse_environment_args "${filtered_args[@]}"
init_environment

# Load postgres environment variables
POSTGRES_ENV_FILE="$ENV_DIR/postgres.env"
source $POSTGRES_ENV_FILE

# Override POSTGRES_VERSION if provided via command line
if [ -n "$postgres_version" ]; then
    POSTGRES_VERSION="$postgres_version"
    echo "Overriding PostgreSQL version with command line value: $POSTGRES_VERSION"
fi

# Validate that POSTGRES_VERSION is set
if [ -z "$POSTGRES_VERSION" ]; then
    echo "Error: PostgreSQL version not specified. Please set POSTGRES_VERSION in $POSTGRES_ENV_FILE or use --postgres-version flag."
    echo "Usage: $0 [--local|--production] [--postgres-version VERSION]"
    exit 1
fi

echo "########################################################"
echo "# Upgrading PostgreSQL Version"
echo "# Environment: ${CODA_ENV}"
echo "# Target version: ${POSTGRES_VERSION}"
echo "# Docker Volume: ${POSTGRES_DATA_VOLUME}"
echo "########################################################"

docker run --rm -e PGAUTO_ONESHOT=yes --env-file $POSTGRES_ENV_FILE -v ${POSTGRES_DATA_VOLUME}:/var/lib/postgresql/data pgautoupgrade/pgautoupgrade:${POSTGRES_VERSION}-alpine
