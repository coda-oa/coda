FROM ghcr.io/astral-sh/uv:0.13-python3.15-trixie-slim

ARG BUILD_ENVIRONMENT=production
ARG APP_HOME=/app
ARG GIT_COMMIT=unknown
ARG GIT_BRANCH=unknown
ARG GIT_TAG=
ARG GIT_REPO=coda-oa/coda
ARG GIT_SHA=unknown

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV BUILD_ENV ${BUILD_ENVIRONMENT}
# The venv lives outside the project and bytecode is compiled at install time.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR ${APP_HOME}

RUN addgroup --system django \
    && adduser --system --ingroup django --home /home/django django

# Pre-create the venv so the unprivileged user can sync into it.
RUN mkdir -p /opt/venv && chown django:django /opt/venv

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
RUN chown -R django:django "${APP_HOME}"
RUN mkdir "${APP_HOME}/staticfiles" && chown -R django:django "${APP_HOME}/staticfiles"
ENV PATH="/home/django/.local/bin:${PATH}"

COPY --chown=django:django src src
RUN mkdir -p "${APP_HOME}/src/coda/apps/media" && chown -R django:django "${APP_HOME}/src/coda/apps/media"
COPY --chown=django:django tests tests
COPY --chown=django:django config config
COPY --chown=django:django manage.py manage.py
COPY --chown=django:django pyproject.toml pyproject.toml
COPY --chown=django:django uv.lock uv.lock
COPY --chown=django:django README.md README.md

RUN echo "${GIT_COMMIT}" > /app/VERSION \
    && echo "${GIT_BRANCH}" > /app/BRANCH \
    && echo "${GIT_TAG}" > /app/TAG \
    && echo "${GIT_REPO}" > /app/REPO \
    && echo "${GIT_SHA}" > /app/SHA

USER django

RUN ls -la /home && ls -la /home/django
RUN uv sync --frozen --no-dev

ENTRYPOINT ["/entrypoint"]
