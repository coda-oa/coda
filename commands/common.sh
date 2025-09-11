export COMPOSE_BASE_CMD="docker compose -f compose.production.yml --env-file $PWD/.envs/.production/coda.env --env-file $PWD/.envs/.production/postgres.env"
