# Updating the Database

This guide explains how to upgrade your PostgreSQL database to a newer version and handle collation version mismatches.

## Overview

CODA provides scripts to safely upgrade PostgreSQL versions and fix database collation issues that can occur after system updates. These automated scripts ensure data integrity while minimizing downtime.


## Upgrading PostgreSQL Version

### Before You Start

**Important:** The upgrade script automatically creates a backup before proceeding, but it's recommended to verify you have recent backups available.

To check existing backups:

```{code-block} bash
./commands/backups.sh --production list
```

Or for local enviroments:

```{code-block} bash
./commands/backups.sh --local list
```

### Running the Upgrade

To upgrade PostgreSQL to a new version, use the upgrade script:

```{code-block} bash
./commands/upgrade-postgres.sh --production --postgres-version <version>
```

**Examples:**

Upgrade to PostgreSQL 17 (Alpine-based):
```{code-block} bash
./commands/upgrade-postgres.sh --production --postgres-version 17
```

Upgrade to PostgreSQL 17 on Debian Bookworm:
```{code-block} bash
./commands/upgrade-postgres.sh --production --postgres-version 17-bookworm
```

Upgrade to a specific Alpine version:
```{code-block} bash
./commands/upgrade-postgres.sh --production --postgres-version 17-alpine3.20
```

### What the Script Does

The upgrade script automatically performs the following steps:

1. **Creates a backup** of your current database
2. **Stops CODA** services to ensure data consistency
3. **Upgrades the database** using [pgautoupgrade](https://github.com/pgautoupgrade/docker-pgautoupgrade)
4. **Updates configuration** to use the new PostgreSQL version
5. **Rebuilds the database container** with the new version
6. **Starts PostgreSQL** and waits for it to be ready
7. **Fixes collation mismatches** automatically (see below)

The entire process typically takes a few minutes, depending on your database size.

### For Local Development

To upgrade a local development database use:

```{code-block} bash
./commands/upgrade-postgres.sh --local --postgres-version <version>
```


## Fixing Collation Version Mismatches

### What is a Collation Mismatch?

Collation version mismatches occur when the operating system's text sorting libraries (glibc/musl) are updated but the database still references the old version. This can happen after:

- PostgreSQL version upgrades
- Operating system updates
- Restoring backups from systems with different OS versions

You might see warnings like:
```
WARNING: database "coda" has a collation version mismatch
DETAIL: The database was created using collation version 2.31, but the operating system provides version 2.36.
```

### Automatic Fixing

The `upgrade-postgres.sh` script automatically fixes collation mismatches. However, you can also run the fix manually if needed.

### Manual Collation Fix

To manually check and fix collation issues:

```{code-block} bash
./commands/fix-collation.sh --production
```

Or for local development:

```{code-block} bash
./commands/fix-collation.sh --local
```

### What the Fix Does

The collation fix script:

1. **Checks all databases** (including system databases like `postgres` and `template1`)
2. **Identifies mismatches** between stored and actual collation versions
3. **Updates collation versions** for affected databases
4. **Reindexes databases** to rebuild indexes with correct collation rules

**Note:** Reindexing can take time for large databases. The script will display which database is currently being processed.


### Database Compatibility

**Important:** PostgreSQL upgrades are forward-compatible but not backward-compatible:

- ✅ Upgrading from PostgreSQL 15 → 17 is supported
- ❌ Downgrading from PostgreSQL 17 → 15 is not supported
- ✅ Restoring old backups (v15) to newer PostgreSQL (v17) works
- ❌ Restoring new backups (v17) to older PostgreSQL (v15) will fail


## After Upgrading

1. **Start CODA services**. The database update script shuts down CODA. After the update is done you have to manually start CODA again, by using the starting script:
   ```{code-block} bash
   ./commands/start-coda.sh --production
   ```
   
   Or for local development:
   ```{code-block} bash
   ./commands/start-coda.sh --local
   ```

2. **Verify the upgrade succeeded** by checking the PostgreSQL version:
   ```{code-block} bash
   docker compose -f compose.production.yml exec postgres psql -U django -d coda -c "SELECT version();"
   ```

3. **Test basic functionality** by accessing CODA and creating/viewing records

4. **Monitor logs** for any unusual warnings or errors

5. **Keep the pre-upgrade backup** for at least a few days as a safety measure


## See Also

- [Installation](installation.md) - Initial CODA setup
- [PostgreSQL Documentation](https://www.postgresql.org/docs/) - Official PostgreSQL documentation