FROM docker.io/python:3.12.3-slim-bookworm as python

ARG BUILD_ENVIRONMENT=production
ARG APP_HOME=/app

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV BUILD_ENV ${BUILD_ENVIRONMENT}

WORKDIR ${APP_HOME}

RUN addgroup --system django \
    && adduser --system --ingroup django --home /home/django django


# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
  # psycopg dependencies
  libpq-dev \
  # Translations dependencies
  gettext \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY --chown=django:django ./dockerfiles/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint

COPY --chown=django:django ./dockerfiles/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

# make django owner of the WORKDIR directory as well.
RUN chown -R django:django ${APP_HOME}
RUN mkdir ${APP_HOME}/staticfiles && chown -R django:django ${APP_HOME}/staticfiles

ENV PATH="/home/django/.local/bin:${PATH}"

COPY --chown=django:django src src
COPY --chown=django:django tests tests
COPY --chown=django:django config config
COPY --chown=django:django manage.py manage.py
COPY --chown=django:django pyproject.toml pyproject.toml
COPY --chown=django:django README.md README.md

USER django

RUN ls -la /home && ls -la /home/django
RUN pip install -U pdm
RUN pdm venv create -n prod && \
    pdm use --venv prod && \
    pdm install --prod


ENTRYPOINT ["/entrypoint"]
