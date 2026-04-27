from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from django.db import models
from django.db.models import Prefetch

from coda.apps.publications.models import Concept as ConceptModel
from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.money import Currency
from coda.domain.vocabulary import VocabularyProtocol


# NOTE: we have to keep this function around for now,
# because migrations don't work well when a previous default value is missing
def empty_vocabulary() -> VocabularyModel:
    return VocabularyModel.empty()


def default_subject_classification_vocabulary() -> int:
    v = VocabularyModel.objects.filter(name="DFG Subject Classification").first()
    if not v:
        return VocabularyModel.empty().pk

    return v.pk


def default_publication_type_vocabulary() -> int:
    v = VocabularyModel.objects.filter(name="COAR Resource Types").first()
    if not v:
        return VocabularyModel.empty().pk

    return v.pk


@dataclass(frozen=True)
class PreloadedVocabularyProvider:
    """A lightweight, immutable provider that holds all three vocabularies
    already fetched from the database.  Satisfies the ``VocabularyProvider``
    protocol without any additional DB queries.

    Obtain an instance via ``GlobalPreferences.preloaded()``.
    """

    _article_publication_type_vocabulary: VocabularyProtocol
    _subject_classification_vocabulary: VocabularyProtocol
    _monograph_publication_type_vocabulary: VocabularyProtocol

    def get_article_publication_type_vocabulary(self) -> VocabularyProtocol:
        return self._article_publication_type_vocabulary

    def get_subject_classification_vocabulary(self) -> VocabularyProtocol:
        return self._subject_classification_vocabulary

    def get_monograph_publication_type_vocabulary(self) -> VocabularyProtocol:
        return self._monograph_publication_type_vocabulary


class GlobalPreferences(models.Model):
    home_currency = models.CharField(max_length=255, default=Currency.EUR.code)
    home_institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Home institution",
    )
    subject_classification_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    article_publication_type_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    monograph_publication_type_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )

    @classmethod
    def _get_prefs_with_vocabularies(cls) -> GlobalPreferences:
        """Fetch the singleton prefs row with all three vocabulary FKs and their
        concepts loaded in a single query + prefetch batches.  Callers that need
        to read vocabulary data should use this instead of bare get_or_create().
        """

        def vocab_prefetches(prefix: str) -> list[Prefetch[Any, Any, Any]]:
            return [
                Prefetch(
                    f"{prefix}__concepts",
                    queryset=ConceptModel.objects.select_related("parent"),
                ),
                Prefetch(
                    f"{prefix}__base_vocabulary",
                    queryset=VocabularyModel.objects.for_domain(),
                ),
            ]

        prefs, _ = (
            cls.objects.select_related(
                "article_publication_type_vocabulary",
                "subject_classification_vocabulary",
                "monograph_publication_type_vocabulary",
            )
            .prefetch_related(
                *vocab_prefetches("article_publication_type_vocabulary"),
                *vocab_prefetches("subject_classification_vocabulary"),
                *vocab_prefetches("monograph_publication_type_vocabulary"),
            )
            .get_or_create()
        )
        return prefs

    @classmethod
    def preloaded(cls) -> PreloadedVocabularyProvider:
        """Return a ``PreloadedVocabularyProvider`` populated with all three
        vocabularies fetched in a single DB round-trip.

        Use this as the ``vocabulary_provider`` argument to
        ``AllowedConcepts.for_*`` factory methods instead of passing the
        ``GlobalPreferences`` class directly, to avoid one DB hit per
        vocabulary accessor call.
        """
        prefs = cls._get_prefs_with_vocabularies()

        # Resolve defaults for any None vocabularies (same logic as the individual statics)
        if prefs.article_publication_type_vocabulary is None:
            prefs.article_publication_type_vocabulary_id = default_publication_type_vocabulary()
            prefs.save()
            prefs = cls._get_prefs_with_vocabularies()
        if prefs.subject_classification_vocabulary is None:
            prefs.subject_classification_vocabulary_id = default_subject_classification_vocabulary()
            prefs.save()
            prefs = cls._get_prefs_with_vocabularies()
        if prefs.monograph_publication_type_vocabulary is None:
            prefs.monograph_publication_type_vocabulary_id = default_publication_type_vocabulary()
            prefs.save()
            prefs = cls._get_prefs_with_vocabularies()

        return PreloadedVocabularyProvider(
            _article_publication_type_vocabulary=vocabulary_repository.as_domain_object(
                cast(VocabularyModel, prefs.article_publication_type_vocabulary)
            ),
            _subject_classification_vocabulary=vocabulary_repository.as_domain_object(
                cast(VocabularyModel, prefs.subject_classification_vocabulary)
            ),
            _monograph_publication_type_vocabulary=vocabulary_repository.as_domain_object(
                cast(VocabularyModel, prefs.monograph_publication_type_vocabulary)
            ),
        )

    @staticmethod
    def get_subject_classification_vocabulary() -> VocabularyProtocol:
        prefs = GlobalPreferences._get_prefs_with_vocabularies()
        if prefs.subject_classification_vocabulary is None:
            prefs.subject_classification_vocabulary_id = default_subject_classification_vocabulary()
            prefs.save()
            prefs = GlobalPreferences._get_prefs_with_vocabularies()

        vocabulary = cast(VocabularyModel, prefs.subject_classification_vocabulary)
        return vocabulary_repository.as_domain_object(vocabulary)

    @staticmethod
    def get_article_publication_type_vocabulary() -> VocabularyProtocol:
        prefs = GlobalPreferences._get_prefs_with_vocabularies()
        if prefs.article_publication_type_vocabulary is None:
            prefs.article_publication_type_vocabulary_id = default_publication_type_vocabulary()
            prefs.save()
            prefs = GlobalPreferences._get_prefs_with_vocabularies()

        vocabulary = cast(VocabularyModel, prefs.article_publication_type_vocabulary)
        return vocabulary_repository.as_domain_object(vocabulary)

    @staticmethod
    def get_monograph_publication_type_vocabulary() -> VocabularyProtocol:
        prefs = GlobalPreferences._get_prefs_with_vocabularies()
        if prefs.monograph_publication_type_vocabulary is None:
            prefs.monograph_publication_type_vocabulary_id = default_publication_type_vocabulary()
            prefs.save()
            prefs = GlobalPreferences._get_prefs_with_vocabularies()

        vocabulary = cast(VocabularyModel, prefs.monograph_publication_type_vocabulary)
        return vocabulary_repository.as_domain_object(vocabulary)

    @staticmethod
    def get_home_currency() -> Currency:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return Currency.from_code(prefs.home_currency)

    @staticmethod
    def set_subject_classification_vocabulary(vocabulary: VocabularyProtocol) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.subject_classification_vocabulary_id = vocabulary.id
        prefs.save()

    @staticmethod
    def set_article_publication_type_vocabulary(vocabulary: VocabularyProtocol) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.article_publication_type_vocabulary_id = vocabulary.id
        prefs.save()

    @staticmethod
    def set_monograph_publication_type_vocabulary(vocabulary: VocabularyProtocol) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.monograph_publication_type_vocabulary_id = vocabulary.id
        prefs.save()

    @staticmethod
    def set_home_currency(currency: Currency) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.home_currency = currency.code
        prefs.save()
