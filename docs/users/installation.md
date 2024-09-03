# Setup

```{admonition} Warning
:class: warning
CODA is still in an early development stage and should not be used in production.
```

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

All that's left is to launch CODA using Docker Compose. CODA offers a `Makefile` with a shorthand command for this purpose. Simply run the following command in a terminal:

```{code-block} bash
make up
```

If `make` is not available on your machine, you can also run the full command yourself:

```{code-block} bash
docker compose -f compose.production.yml --env-file .envs/.production/coda.env up -d
```

Even though this step appears to finish quickly, it can take a couple of minutes before CODA is accessible in your web browser. This happens because CODA needs to establish its Journal, Publisher and Contracts database on startup.


### Creating a superuser

After CODA has launched, you need to create a superuser to log in and create other users.
Run the following shorthand command in your shell:

```{code-block} bash
make superuser
```

Or run the full command yourself:

```{code-block} bash
docker compose -f compose.production.yml --env-file .envs/.production/coda.env exec django pdm run manage.py createsuperuser
```

After creating a superuser, you should be able to log into CODA from your web browser.