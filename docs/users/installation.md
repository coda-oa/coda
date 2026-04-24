# Setup

## Prerequisites

CODA is designed to run in Docker containers. Therefore, [Docker](https://docker.com) is mandatory to run it.
While it can run outside of Docker containers, we will not provide any support for it.
It is recommended to use a Linux machine to run CODA.


## Getting CODA

As we do not provide any pre-built Docker images yet, the easiest way to get CODA is to clone the Git repository by entering the following command into a shell.

```{code-block} bash
git clone https://github.com/coda-oa/coda
```

After cloning the repository, open the newly created `coda` directory.


## Preparing environment variables

CODA uses environment variable files to configure certain settings.
The variable files you need to edit are located in the `.envs/.production` directory.


### coda.env

In `coda.env` you can set which port CODA will be run under by adjusting the `CODA_EXPOSED_PORT` variable.


### django.env

In `django.env` you must set the following variables:

```{code-block}
DJANGO_SECRET_KEY=<your-secret-key>
DJANGO_ALLOWED_HOSTS=<your-allowed-hosts>
DJANGO_CSRF_TRUSTED_ORIGINS=<your-trusted-origins>
```

`DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` should generally point to the same hosts. For example if CODA is running on the address `coda.example.com` then these variable could look as follows:

```
DJANGO_ALLOWED_HOSTS=coda.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://coda.example.com
```

For more information about these values, see the official Django documentation: 
- [Secret Key](https://docs.djangoproject.com/en/5.1/ref/settings/#secret-key)
- [Allowed Hosts](https://docs.djangoproject.com/en/5.1/ref/settings/#allowed-hosts)
- [CSRF Trusted Origins](https://docs.djangoproject.com/en/5.1/ref/settings/#csrf-trusted-origins)

It is recommended to comment out unused variables with a leading `#`


### postgres.env

In `postgres.env` you need to set a password for the database:

```{code-block}
POSTGRES_PASSWORD=<your-password>
```

## Launching CODA

All that's left is to launch CODA using the provided startup script. Simply run the following command in a terminal from the CODA directory:

```{code-block} bash
./commands/start-coda.sh --production
```

Or for a local development environment:

```{code-block} bash
./commands/start-coda.sh --local
```



Even though this step appears to finish quickly, it can take a couple of minutes before CODA is accessible in your web browser. This happens because CODA needs to establish its Journal, Publisher and Contracts database on startup.


### Creating a superuser

After CODA has launched, you need to create a superuser to log in and [create other users](usercreation.md).
Run the following command in your shell:

```{code-block} bash
./commands/create-superuser.sh --production
```

Or for local environment:

```{code-block} bash
./commands/create-superuser.sh --local
```

After creating a superuser, you should be able to log into CODA from your web browser.


## Stopping CODA

To stop CODA, use the stop script:

```{code-block} bash
./commands/stop-coda.sh --production
```

Or for local environment:

```{code-block} bash
./commands/stop-coda.sh --local
```

## Backups

CODA provides a built-in backup system to protect your database. It's highly recommended to create regular backups of your CODA installation.

### Creating a Backup

To create a new database backup:

```{code-block} bash
./commands/backups.sh --production create
```

Or for local environment:

```{code-block} bash
./commands/backups.sh --local create
```

The backup will be automatically timestamped and stored in the PostgreSQL backup directory.

### Listing Available Backups

To see all available backups:

```{code-block} bash
./commands/backups.sh --production list
```

Or for local environment:

```{code-block} bash
./commands/backups.sh --local list
```

This will display all backup files with their names and creation dates.

### Restoring from a Backup

To restore CODA from a previous backup:

```{code-block} bash
./commands/backups.sh --production restore <backup_name>
```

Or for local environment:

```{code-block} bash
./commands/backups.sh --local restore <backup_name>
```

Replace `<backup_name>` with the exact name from the backup list (e.g., `backup_2026_01_21_143022.sql.gz`).

```{admonition} Important
:class: warning
The restore process will automatically:
1. Stop the Django service to prevent database access
2. Ensure PostgreSQL is running
3. Restore the database from the backup file
4. You'll need to restart CODA afterward using `./commands/start-coda.sh --production`
```

