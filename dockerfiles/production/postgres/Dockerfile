# check=skip=InvalidDefaultArgInFrom
ARG POSTGRES_VERSION
FROM postgres:${POSTGRES_VERSION}

COPY ./dockerfiles/production/postgres/maintenance /usr/local/bin/maintenance
RUN chmod +x /usr/local/bin/maintenance/*
RUN mv /usr/local/bin/maintenance/* /usr/local/bin \
    && rmdir /usr/local/bin/maintenance
