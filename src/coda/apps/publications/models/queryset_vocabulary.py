from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Prefetch

if TYPE_CHECKING:
    from ._vocabulary import Vocabulary  # noqa

MAX_VOCABULARY_NESTING_DEPTH = 10


class VocabularyQuerySet(models.QuerySet["Vocabulary"]):
    def for_domain(self, _depth: int = MAX_VOCABULARY_NESTING_DEPTH) -> VocabularyQuerySet:
        """Prefetch all relations needed to hydrate a Vocabulary domain object.

        Recursively prefetches base_vocabulary chains and their concepts up to
        MAX_VOCABULARY_NESTING_DEPTH levels deep.
        """
        from coda.apps.publications.models._vocabulary import Concept as ConceptModel
        from coda.apps.publications.models._vocabulary import Vocabulary as VocabularyModel

        qs = self.prefetch_related(
            Prefetch(
                "concepts",
                queryset=ConceptModel.objects.select_related("parent"),
            ),
        )

        if _depth > 0:
            qs = qs.prefetch_related(
                Prefetch(
                    "base_vocabulary",
                    queryset=VocabularyModel.objects.for_domain(_depth=_depth - 1),
                ),
            )

        return qs


class VocabularyManager(models.Manager["Vocabulary"]):
    def get_queryset(self) -> VocabularyQuerySet:
        return VocabularyQuerySet(self.model, using=self._db)

    def for_domain(self, _depth: int = MAX_VOCABULARY_NESTING_DEPTH) -> VocabularyQuerySet:
        return self.get_queryset().for_domain(_depth=_depth)
