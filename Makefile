ENV:=production

up:
	docker compose -f compose.${ENV}.yml up -d

down:
	docker compose -f compose.${ENV}.yml down

superuser:
	docker compose -f compose.${ENV}.yml exec django pdm run manage.py createsuperuser

backup:
	docker compose -f compose.${ENV}.yml exec postgres backup

list-backups:
	docker compose -f compose.${ENV}.yml exec postgres backups

restore:
	docker compose -f compose.${ENV}.yml exec postgres restore
