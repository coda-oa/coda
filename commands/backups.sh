script_dir="$(cd "$(dirname "$0")" && pwd)"
source ${script_dir}/common.sh


if [[ $1 = "create" ]]; then
  cmd="backup"
elif [[ $1 = "list" ]]; then
  cmd="backups"
elif [[ $1 = "restore" ]]; then
  echo "Shutting down CODA to restore backup..."
  $COMPOSE_BASE_CMD stop django
  echo "Ensuring postgres service is running for restore..."
  $COMPOSE_BASE_CMD up -d postgres
  cmd="restore $2"
else
  echo "Invalid command $1"
  exit 1
fi


$COMPOSE_BASE_CMD run --rm -it postgres $cmd 
