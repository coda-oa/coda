# Updating CODA

This guide explains how to update your CODA installation to the latest version.

```{admonition} Important
:class: warning
Always create a backup before updating CODA to ensure you can restore your data if something goes wrong.
```

## Prerequisites

- A running CODA installation
- Access to the CODA directory
- Git installed on your system

## Update Process

### 1. Create a Backup

Before updating, create a backup of your database:

```{code-block} bash
./commands/backups.sh --production create
```

Or for local environment:

```{code-block} bash
./commands/backups.sh --local create
```

For more information about backups, see the [Backups section](installation.md#backups) in the Installation guide.

### 2. Stop CODA

Stop the running CODA instance:

```{code-block} bash
./commands/stop-coda.sh --production
```

Or for local environment:

```{code-block} bash
./commands/stop-coda.sh --local
```

### 3. Pull Latest Changes

Update your local repository with the latest changes from the Git repository:

```{code-block} bash
git pull origin main
```

```{admonition} Note
:class: tip
If you're tracking a different branch or have customizations, adjust the git command accordingly. For example, if you're on a `stable` branch, use `git pull origin stable`.
```

### 4. Restart CODA

Start CODA with the updated code. The `--build` flag ensures that Docker containers are rebuilt with the latest changes:

```{code-block} bash
./commands/start-coda.sh --production
```

Or for local environment:

```{code-block} bash
./commands/start-coda.sh --local
```

The startup script automatically rebuilds the containers and applies any necessary database migrations.

### 5. Verify the Update

After CODA restarts, verify that:

1. CODA is accessible in your web browser
2. You can log in successfully
3. Your data is intact
4. All features are working as expected

## Troubleshooting

### Update Failed

If the update fails or CODA doesn't start properly:

1. Check the logs for error messages:
   ```{code-block} bash
   docker compose -f compose.production.yml logs
   ```

2. If necessary, restore from your backup:
   ```{code-block} bash
   ./commands/backups.sh --production restore <backup_name>
   ```

3. Then restart CODA:
   ```{code-block} bash
   ./commands/start-coda.sh --production
   ```

### Checking Available Updates

To check if updates are available before pulling:

```{code-block} bash
git fetch origin
git log HEAD..origin/main --oneline
```

This shows you what commits are available for download.

