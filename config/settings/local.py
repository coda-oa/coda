from .base import *
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True

# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="!!!SET DJANGO_SECRET_KEY!!!",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["localhost", "0.0.0.0", "127.0.0.1"]
INTERNAL_IPS = [
    "127.0.0.1",
]


# https://docs.djangoproject.com/en/dev/ref/settings/#mailers
MAILERS["default"]["BACKEND"] = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# Silk
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["silk"]
MIDDLEWARE += ["silk.middleware.SilkyMiddleware"]

# Django Debug Toolbar
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
# fix for docker internal IPs.
# https://github.com/cookiecutter/cookiecutter-django/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/config/settings/local.py
import socket

hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
INTERNAL_IPS += [".".join([*ip.split(".")[:-1], "1"]) for ip in ips]
