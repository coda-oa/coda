#!/bin/bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"

# Shared state between step functions
STASH_REF=""
STASH_MSG="update-coda pre-update"
ROLLBACK_ON_EXIT=false
CODA_STOPPED=false
CODA_RESTARTED=false

# True only while the slot STASH_REF still holds this run's tagged entry.
# Guards against another stash landing on top of ours between push and pop.
_stash_is_mine() {
  [[ -n "$STASH_REF" ]] && [[ "$(git stash list -1 --format=%s "$STASH_REF" 2>/dev/null)" == *"$STASH_MSG"* ]]
}

# Cleanup: restart CODA if it was stopped but not restarted
cleanup() {
  local status=$?
  if [[ "$ROLLBACK_ON_EXIT" == true ]]; then
    echo "Rolling back to the previous branch and restoring stashed changes..." >&2
    git checkout - 2>/dev/null || true
    if [[ -n "$STASH_REF" ]]; then
      if _stash_is_mine; then
        git stash pop "$STASH_REF" 2>/dev/null || true
      else
        echo "Stash queue changed; your changes remain under '$STASH_MSG' in 'git stash list'." >&2
      fi
    fi
  fi
  if [[ "$CODA_STOPPED" == true && "$CODA_RESTARTED" == false ]]; then
    echo "Warning: CODA was stopped but the update failed. Restarting..." >&2
    "${script_dir}/start-coda.sh" --"$CODA_ENV" || true
  fi
  return "$status"
}
trap cleanup EXIT

# Custom usage for update script
show_update_usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Environment Options:"
  echo "  --local, -l          Use local environment (compose.local.yml)"
  echo "  --production, -p     Use production environment (compose.production.yml)"
  echo "  --env ENV            Specify environment explicitly (local|production)"
  echo ""
  echo "Update Options:"
  echo "  --branch BRANCH      Git branch to pull from (default: stable)"
  echo "  --backup             Create backup before updating"
  echo "  --no-backup          Skip backup creation (default)"
  echo "  --help, -h           Show this help message"
  echo ""
  echo "Examples:"
  echo "  $0 --production --backup"
  echo "  $0 --local --branch develop"
  echo "  $0 --production --backup --branch stable"

  return 0
}

# Parse update-specific arguments
parse_update_args() {
  BRANCH="stable"
  CREATE_BACKUP=false

  while [[ $# -gt 0 ]]; do
    local arg="$1"
    case "$arg" in
    --branch)
      local branch_value="${2:-}"
      if [[ -z "$branch_value" || "$branch_value" == --* ]]; then
        echo "Error: --branch requires a value" >&2
        exit 1
      fi
      BRANCH="$branch_value"
      shift 2
      ;;
    --backup)
      CREATE_BACKUP=true
      shift
      ;;
    --no-backup)
      CREATE_BACKUP=false
      shift
      ;;
    --help | -h)
      show_update_usage
      exit 0
      ;;
    *)
      # Pass to common.sh for environment parsing
      shift
      ;;
    esac
  done

  return 0
}

# Parse arguments before sourcing common.sh
parse_update_args "$@"

# Source common.sh for environment setup (pure library: define only)
source "${script_dir}/common.sh"
parse_environment_args "$@"
init_environment

has_uncommitted_changes() {
  if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    return 0
  fi
  return 1
}

preflight_checks() {
  # Check git is installed
  if ! command -v git >/dev/null 2>&1; then
    echo "Error: git is not installed." >&2
    exit 1
  fi

  # Check we're inside a git repo
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Error: Not inside a git repository." >&2
    exit 1
  fi

  # Check the target branch exists remotely
  if ! git ls-remote origin "$BRANCH" | grep -q "refs/heads/$BRANCH"; then
    echo "Error: Branch '$BRANCH' does not exist on remote 'origin'." >&2
    exit 1
  fi

  # Check for uncommitted changes
  if has_uncommitted_changes; then
    echo "Warning: There are uncommitted changes in the repository."
    echo "These will be stashed before switching branches."
    echo ""
  fi
  return 0
}

step_create_backup() {
  if [[ "$CREATE_BACKUP" == true ]]; then
    echo "Step 1/5: Creating backup..."
    if ! "${script_dir}/backups.sh" --"$CODA_ENV" create; then
      echo "Error: Backup failed. Aborting update." >&2
      return 1
    fi
    echo ""
  else
    echo "Step 1/5: Skipping backup (use --backup to create one)"
    echo ""
  fi
}

step_stop_coda() {
  echo "Step 2/5: Stopping CODA..."
  if ! "${script_dir}/stop-coda.sh" --"$CODA_ENV"; then
    echo "Error: Failed to stop CODA. Aborting update." >&2
    return 1
  fi
  CODA_STOPPED=true
  echo ""
}

step_fetch_and_switch() {
  echo "Step 3/5: Fetching and switching to branch '$BRANCH'..."
  if has_uncommitted_changes; then
    echo "Stashing uncommitted changes..."
    git stash push --include-untracked -m "$STASH_MSG"
    STASH_REF="stash@{0}"
  fi
  if ! git fetch origin "$BRANCH"; then
    echo "Error: Fetching '$BRANCH' from origin failed. Aborting update." >&2
    return 1
  fi
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
  else
    echo "Branch '$BRANCH' not found locally, creating it from remote..."
    git checkout -b "$BRANCH" "origin/$BRANCH"
  fi
  echo ""
}

step_pull_and_restore() {
  echo "Step 4/5: Pulling latest changes and restoring stashed changes..."
  if ! git pull origin "$BRANCH"; then
    echo "Error: Git pull failed. Original branch and local changes will be restored." >&2
    ROLLBACK_ON_EXIT=true
    return 1
  fi

  # Restore stashed changes if we created one in this run
  if [[ -n "$STASH_REF" ]]; then
    if _stash_is_mine; then
      if ! git stash pop "$STASH_REF" 2>&1; then
        echo "Warning: Stash restore had conflicts." >&2
        echo "Your local changes may need manual conflict resolution." >&2
      fi
    else
      echo "Warning: The stash queue changed during the update." >&2
      echo "Your changes are safe under '$STASH_MSG' — see 'git stash list'." >&2
    fi
  fi
  echo ""
}

step_start_coda() {
  echo "Step 5/5: Starting CODA (this will rebuild containers and run migrations)..."
  if ! "${script_dir}/start-coda.sh" --"$CODA_ENV"; then
    echo "Error: Failed to start CODA." >&2
    return 1
  fi
  CODA_RESTARTED=true
  echo ""
}

update_coda() {
  # Ensure we operate from the repo root, regardless of caller's CWD
  REPO_ROOT="$(dirname "$script_dir")"
  cd "$REPO_ROOT" || {
    echo "Error: Cannot access repository root at $REPO_ROOT" >&2
    exit 1
  }

  # Run preflight checks before stopping any services
  preflight_checks

  echo "CODA Update Script"
  echo "Environment: $CODA_ENV"
  echo "Branch: $BRANCH"
  echo "Backup: $([[ "$CREATE_BACKUP" == true ]] && echo "Yes" || echo "No")"
  echo ""

  step_create_backup
  step_stop_coda
  step_fetch_and_switch
  step_pull_and_restore
  step_start_coda

  echo "Update completed successfully!"
  echo ""
  echo "Next steps:"
  echo "1. Verify CODA is accessible in your web browser"
  echo "2. Check that you can log in successfully"
  echo "3. Verify that your data is intact"
  echo ""
  if [[ "$CREATE_BACKUP" == true ]]; then
    echo "Note: A backup was created before the update."
    echo "You can list backups with: ./commands/backups.sh --${CODA_ENV} list"
    echo ""
  fi

  return 0
}

update_coda
