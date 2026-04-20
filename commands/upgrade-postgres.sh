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

echo ""
echo "# Creating backup of PostgreSQL data volume ${POSTGRES_DATA_VOLUME}..."
echo ""

$PWD/commands/backups.sh create --${CODA_ENV}

echo "Shutting down CODA before PostgreSQL upgrade"
source ${script_dir}/stop-coda.sh
stop_coda

# Determine pgautoupgrade image tag
# Handle formats: "15", "15-alpine", "15-alpine3.18", "15-bookworm", "15-bullseye", etc.
# Strategy: If POSTGRES_VERSION contains a dash, it already has an OS/variant suffix
if [[ $POSTGRES_VERSION == *"-"* ]]; then
    # Already has suffix (e.g., "15-alpine", "17-bookworm"), use as-is
    PGAUTOUPGRADE_TAG="${POSTGRES_VERSION}"
else
    # Just version number (e.g., "15"), default to alpine
    PGAUTOUPGRADE_TAG="${POSTGRES_VERSION}-alpine"
fi

echo "Using pgautoupgrade image: pgautoupgrade/pgautoupgrade:${PGAUTOUPGRADE_TAG}"
docker run --rm -e PGAUTO_ONESHOT=yes --env-file $POSTGRES_ENV_FILE -v ${POSTGRES_DATA_VOLUME}:/var/lib/postgresql/data pgautoupgrade/pgautoupgrade:${PGAUTOUPGRADE_TAG}

echo ""
echo "# PostgreSQL upgrade completed. Updating environment and rebuilding container..."
echo ""

# Update the POSTGRES_VERSION in the env file to match the upgraded version
sed -i "s/^POSTGRES_VERSION=.*/POSTGRES_VERSION=${POSTGRES_VERSION}/" "$POSTGRES_ENV_FILE"

# Rebuild postgres image with new version
POSTGRES_VERSION=${POSTGRES_VERSION} docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE build --build-arg POSTGRES_VERSION=${POSTGRES_VERSION} postgres

echo ""
echo "# Starting PostgreSQL ${POSTGRES_VERSION} and checking collation version..."
echo ""

# Start with the new version
POSTGRES_VERSION=${POSTGRES_VERSION} docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE up -d postgres

# Wait for postgres to be ready (with retries)
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if POSTGRES_VERSION=${POSTGRES_VERSION} docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE exec -T postgres pg_isready -U django > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# Run collation fix
POSTGRES_VERSION=${POSTGRES_VERSION} docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE run --rm postgres fix-collation
