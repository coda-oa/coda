from typing import cast
from django.db import models

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

    @staticmethod
    def get_subject_classification_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        if prefs.subject_classification_vocabulary is None:
            prefs.subject_classification_vocabulary_id = default_subject_classification_vocabulary()
            prefs.save()

        vocabulary = cast(VocabularyModel, prefs.subject_classification_vocabulary)
        return vocabulary_repository.as_domain_object(vocabulary)

    @staticmethod
    def get_article_publication_type_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        if prefs.article_publication_type_vocabulary is None:
            prefs.article_publication_type_vocabulary_id = default_publication_type_vocabulary()
            prefs.save()

        vocabulary = cast(VocabularyModel, prefs.article_publication_type_vocabulary)
        return vocabulary_repository.as_domain_object(vocabulary)

    @staticmethod
    def get_monograph_publication_type_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        if prefs.monograph_publication_type_vocabulary is None:
            prefs.monograph_publication_type_vocabulary_id = default_publication_type_vocabulary()
            prefs.save()

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
