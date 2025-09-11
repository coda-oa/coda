#!/bin/bash

COMPOSE_PROJECT_NAME=$(basename $PWD)
POSTGRES_DATA_VOLUME=${COMPOSE_PROJECT_NAME}_production_postgres_data
POSTGRES_ENV_FILE=$PWD/.envs/.production/postgres.env
source $POSTGRES_ENV_FILE

echo "########################################################"
echo "# Upgrading PostgreSQL Version"
echo "# Target version: ${POSTGRES_VERSION}"
echo "# Docker Volume: ${POSTGRES_DATA_VOLUME}"
echo "########################################################"


docker run --rm -e PGAUTO_ONESHOT=yes --env-file $POSTGRES_ENV_FILE -v ${POSTGRES_DATA_VOLUME}:/var/lib/postgresql/data pgautoupgrade/pgautoupgrade:${POSTGRES_VERSION}-alpine
