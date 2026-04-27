from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from coda.apps.authors.models import Author  # noqa


class AuthorQuerySet(models.QuerySet["Author"]):
    def for_domain(self) -> AuthorQuerySet:
        """Prefetch all relations needed to hydrate an Author domain object."""
        return self.select_related("identifier", "affiliation")


class AuthorManager(models.Manager["Author"]):
    def get_queryset(self) -> AuthorQuerySet:
        return AuthorQuerySet(self.model, using=self._db)

    def for_domain(self) -> AuthorQuerySet:
        return self.get_queryset().for_domain()
