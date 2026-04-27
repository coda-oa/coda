from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Prefetch

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.publications.models._vocabulary import Vocabulary as VocabularyModel

if TYPE_CHECKING:
    from ._publication import Publication  # noqa


class PublicationQuerySet(models.QuerySet["Publication"]):
    def for_domain(self) -> PublicationQuerySet:
        """Prefetch all relations needed to hydrate a Publication domain object."""
        return self.select_related(
            "article_journal",
            "article_journal__publisher",
            "monograph_publisher",
            "publication_type",
            "subject_area",
        ).prefetch_related(
            Prefetch(
                "publication_type__vocabulary",
                queryset=VocabularyModel.objects.for_domain(),
            ),
            Prefetch(
                "subject_area__vocabulary",
                queryset=VocabularyModel.objects.for_domain(),
            ),
            Prefetch(
                "relevant_authors",
                queryset=AuthorModel.objects.for_domain(),
            ),
            "attached_contracts",
            "links__type",
        )


class PublicationManager(models.Manager["Publication"]):
    def get_queryset(self) -> PublicationQuerySet:
        return PublicationQuerySet(self.model, using=self._db)

    def for_domain(self) -> PublicationQuerySet:
        return self.get_queryset().for_domain()
