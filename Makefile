ENV:=production
SERVICE:=

up:
	docker compose -f compose.${ENV}.yml --env-file .envs/.${ENV}/coda.env up -d ${SERVICE}

down:
	docker compose -f compose.${ENV}.yml --env-file .envs/.${ENV}/coda.env down ${SERVICE}

superuser:
	docker compose -f compose.${ENV}.yml --env-file .envs/.${ENV}/coda.env exec django pdm run manage.py createsuperuser

backup:
	docker compose -f compose.${ENV}.yml --env-file .envs/.${ENV}/coda.env exec postgres backup

list-backups:
	docker compose -f compose.${ENV}.yml --env-file .envs/.${ENV}/coda.env exec postgres backups

restore:
	docker compose -f compose.${ENV}.yml --env-file .envs/.${ENV}/coda.env exec postgres restore
