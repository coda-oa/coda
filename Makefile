ENV:=production

superuser:
	docker compose -f compose.${ENV}.yml exec django pdm run manage.py createsuperuser

backup:
	docker compose -f compose.${ENV}.yml exec postgres backup

list-backups:
	docker compose -f compose.${ENV}.yml exec postgres backups

restore:
	docker compose -f compose.${ENV}.yml exec postgres restore
