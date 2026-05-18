#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

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
      if [[ -z "$2" || "$2" == --* ]]; then
        echo "Error: --branch requires a value" >&2
        exit 1
      fi
      BRANCH="$2"
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

# Source common.sh for environment setup
source ${script_dir}/common.sh "$@"

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

  # Step 1: Create backup if requested
  if [[ "$CREATE_BACKUP" == true ]]; then
    echo "Step 1/5: Creating backup..."
    ${script_dir}/backups.sh --${CODA_ENV} create
    if [[ $? -ne 0 ]]; then
      echo "Error: Backup failed. Aborting update." >&2
      exit 1
    fi
    echo ""
  else
    echo "Step 1/5: Skipping backup (use --backup to create one)"
    echo ""
  fi

  # Step 2: Stop CODA
  echo "Step 2/5: Stopping CODA..."
  ${script_dir}/stop-coda.sh --${CODA_ENV}
  if [[ $? -ne 0 ]]; then
    echo "Error: Failed to stop CODA. Aborting update." >&2
    exit 1
  fi
  echo ""

  # Step 3: Fetch and switch to the target branch
  echo "Step 3/5: Fetching and switching to branch '$BRANCH'..."
  if has_uncommitted_changes; then
    echo "Stashing uncommitted changes..."
    git stash push --include-untracked
  fi
  git fetch origin "$BRANCH"
  if ! git checkout "$BRANCH" 2>/dev/null; then
    echo "Branch '$BRANCH' not found locally, creating it from remote..."
    git checkout -b "$BRANCH" "origin/$BRANCH"
  fi
  echo ""

  # Step 4: Pull latest changes and restore stashed changes
  echo "Step 4/5: Pulling latest changes and restoring stashed changes..."
  git pull origin "$BRANCH"
  if [[ $? -ne 0 ]]; then
    echo "Error: Git pull failed. Restoring original branch..." >&2
    git checkout - 2>/dev/null || true
    git stash pop 2>/dev/null || true
    ${script_dir}/start-coda.sh --${CODA_ENV}
    exit 1
  fi

  # Restore stashed changes if they exist
  if git stash list 2>/dev/null | grep -q .; then
    if ! git stash pop 2>&1; then
      echo "Warning: Stash restore had conflicts." >&2
      echo "Your local changes may need manual conflict resolution." >&2
    fi
  fi
  echo ""

  # Step 5: Start CODA
  echo "Step 5/5: Starting CODA (this will rebuild containers and run migrations)..."
  ${script_dir}/start-coda.sh --${CODA_ENV}
  if [[ $? -ne 0 ]]; then
    echo "Error: Failed to start CODA." >&2
    exit 1
  fi
  echo ""

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
