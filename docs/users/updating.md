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

## Checking Available Updates

CODA automatically checks for new commits on GitHub.
If a newer version is available, a colored banner appears in the left
navigation bar with a link to the changes on GitHub.

To manually check for updates before pulling:

```{code-block} bash
git fetch origin
git log HEAD..origin/main --oneline
```

This shows you what commits are available for download.

## Update Process

You can update CODA either using the automated update script or by running each step manually.

### Option 1: Automated Update (Recommended)

The easiest way to update CODA is using the automated update script:

```{code-block} bash
./commands/update-coda.sh --production --backup
```

Or for local environment:

```{code-block} bash
./commands/update-coda.sh --local --backup
```

The script automatically performs all necessary steps: creating a backup (if `--backup` is specified), stopping CODA, pulling the latest changes, and restarting with the updated code. CODA must be already running to use this automated approach. 

#### Update Script Options

- `--production` or `--local`: Specify the environment
- `--backup`: Create a backup before updating (recommended)
- `--branch BRANCH`: Pull from a specific branch (default: `stable`)

Examples:

```{code-block} bash
# Production update with backup from stable branch
./commands/update-coda.sh --production --backup

# Local update from develop branch
./commands/update-coda.sh --local --branch develop

# Production update without backup
./commands/update-coda.sh --production
```

### Option 2: Manual Update

If you prefer to run each step manually, follow these steps:

#### 1. Create a Backup

Before updating, create a backup of your database:

```{code-block} bash
./commands/backups.sh --production create
```

Or for local environment:

```{code-block} bash
./commands/backups.sh --local create
```

For more information about backups, see the [Backups section](installation.md#backups) in the Installation guide.

#### 2. Stop CODA

Stop the running CODA instance:

```{code-block} bash
./commands/stop-coda.sh --production
```

Or for local environment:

```{code-block} bash
./commands/stop-coda.sh --local
```

#### 3. Pull Latest Changes

Update your local repository with the latest changes from the Git repository:

```{code-block} bash
git pull origin stable
```

```{admonition} Note
:class: tip
The `stable` branch is the default and recommended option. You can pull it as shown above. If you need access to more recent changes, you can alternatively pull from the `develop` branch using `git pull origin develop`.
```

#### 4. Restart CODA

Start CODA with the updated code by running the start command:

```{code-block} bash
./commands/start-coda.sh --production
```

Or for local environment:

```{code-block} bash
./commands/start-coda.sh --local
```

The startup script automatically rebuilds the containers and applies any necessary database migrations.

#### 5. Verify the Update

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


## Update PostgreSQL Version

If you pull a new release that requires an upgrade of the PostgreSQL version (mentioned in the release notes), you have to also run the `upgrade-postgres` command. 

Before you start, it's recommended to verify you have recent backups available. 

To check existing backups:

```{code-block} bash
./commands/backups.sh --production list
```

Or for local enviroments:

```{code-block} bash
./commands/backups.sh --local list
```

### Running the Upgrade

To upgrade PostgreSQL to a new version, use the upgrade:

```{code-block} bash
./commands/upgrade-postgres.sh --production
```

Or for local enviroments:

```{code-block} bash
./commands/upgrade-postgres.sh --local 
```

### What the Script Does

The upgrade script automatically performs the following steps:

1. **Creates a backup** of your current database
2. **Stops CODA** services to ensure data consistency
3. **Upgrades the database** using [pgautoupgrade](https://github.com/pgautoupgrade/docker-pgautoupgrade)
4. **Rebuilds the database container** with the new version
5. **Starts PostgreSQL** and waits for it to be ready
6. **Fixes collation mismatches** automatically if any (see below)

The entire process typically takes a few minutes, depending on your database size.

### Fixing Collation Version Mismatches

If there is a major version step between the PostgreSQL versions, it is possible that you face a `collation version mismatch` error. 

You might see warnings like:
```
WARNING: database "coda" has a collation version mismatch
DETAIL: The database was created using collation version 2.31, but the operating system provides version 2.36.
```

The `upgrade-postgres.sh` script automatically fixes collation mismatches. However, you can also run the fix manually if needed: 

```{code-block} bash
./commands/fix-collation.sh --production
```

Or for local development:

```{code-block} bash
./commands/fix-collation.sh --local
```

### After Upgrading

**Start CODA services**. The database update script shuts down CODA. After the update is done you have to manually start CODA again, by using the starting script:

```{code-block} bash
./commands/start-coda.sh --production
```

Or for local development:

```{code-block} bash
./commands/start-coda.sh --local
```

It is recommended to **keep the pre-upgrade backup** for at least a few days as a safety measure
