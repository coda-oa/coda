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
		if [ -z "${2:-}" ]; then
			echo "Error: --postgres-version requires a value." >&2
			exit 1
		fi
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

# Resolve the real compose-managed volume: key from the compose file itself,
# actual name from Docker's labels (immune to project/checkout renames).
VOLUME_KEYS="$($COMPOSE_BASE_CMD config --volumes | grep -E '_postgres_data$')"
if [ "$(printf '%s\n' "$VOLUME_KEYS" | wc -l)" -ne 1 ]; then
	echo "Error: expected exactly one *_postgres_data volume in $COMPOSE_FILE, got:" >&2
	echo "$VOLUME_KEYS" >&2
	exit 1
fi
POSTGRES_DATA_VOLUME="$(docker volume ls -q --filter "label=com.docker.compose.volume=${VOLUME_KEYS}" | head -1)"
if [ -z "$POSTGRES_DATA_VOLUME" ]; then
	echo "Error: no compose-managed volume '${VOLUME_KEYS}' found. Aborting before any destructive step." >&2
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

echo "Using pgautoupgrade image: pgautoupgrade/pgautoupgrade:${POSTGRES_VERSION}"
docker run --rm -e PGAUTO_ONESHOT=yes --env-file $POSTGRES_ENV_FILE -v ${POSTGRES_DATA_VOLUME}:/var/lib/postgresql/data pgautoupgrade/pgautoupgrade:${POSTGRES_VERSION}

echo ""
echo "# PostgreSQL upgrade completed. Rebuilding container with new version..."
echo ""

# Rebuild postgres image with new version
docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE build --build-arg POSTGRES_VERSION=${POSTGRES_VERSION} postgres

echo ""
echo "# Starting PostgreSQL ${POSTGRES_VERSION} and checking collation version..."
echo ""

# Start with the new version
docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE up -d postgres

# Wait for postgres to be ready (with retries)
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE exec -T postgres pg_isready -U django > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# Run collation fix
docker compose -f $COMPOSE_FILE --env-file $ENV_DIR/coda.env --env-file $POSTGRES_ENV_FILE run --rm postgres fix-collation
