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
        return VocabularyModel.empty().id

    return v.id


def default_publication_type_vocabulary() -> int:
    v = VocabularyModel.objects.filter(name="COAR Resource Types").first()
    if not v:
        return VocabularyModel.empty().id

    return v.id


class GlobalPreferences(models.Model):
    home_currency = models.CharField(max_length=255, default=Currency.EUR.code)
    subject_classification_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_DEFAULT,
        default=default_subject_classification_vocabulary,
        related_name="+",
    )
    article_publication_type_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_DEFAULT,
        default=default_publication_type_vocabulary,
        related_name="+",
    )
    monograph_publication_type_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_DEFAULT,
        default=default_publication_type_vocabulary,
        related_name="+",
    )

    @staticmethod
    def get_subject_classification_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return vocabulary_repository.as_domain_object(prefs.subject_classification_vocabulary)

    @staticmethod
    def get_article_publication_type_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return vocabulary_repository.as_domain_object(prefs.article_publication_type_vocabulary)

    @staticmethod
    def get_monograph_publication_type_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return vocabulary_repository.as_domain_object(prefs.monograph_publication_type_vocabulary)

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
