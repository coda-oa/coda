from django.db import models

from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.apps.publications.repositories import vocabulary_repository
from coda.money import Currency
from coda.vocabulary import VocabularyProtocol


# NOTE: we have to keep this function around for now,
# because migrations don't work well when a previous default value is missing
def empty_vocabulary() -> VocabularyModel:
    return VocabularyModel.empty()


def default_subject_classification_vocabulary() -> VocabularyModel:
    v = VocabularyModel.objects.filter(name="DFG Subject Classification").first()
    if not v:
        return VocabularyModel.empty()

    return v


def default_publication_type_vocabulary() -> VocabularyModel:
    v = VocabularyModel.objects.filter(name="COAR Resource Types").first()
    if not v:
        return VocabularyModel.empty()

    return v


class GlobalPreferences(models.Model):
    home_currency = models.CharField(max_length=255, default=Currency.EUR.code)
    default_subject_classification_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_DEFAULT,
        default=default_subject_classification_vocabulary,
        related_name="+",
    )
    default_publication_type_vocabulary = models.ForeignKey(
        VocabularyModel,
        on_delete=models.SET_DEFAULT,
        default=default_publication_type_vocabulary,
        related_name="+",
    )

    @staticmethod
    def get_subject_classification_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return vocabulary_repository.as_domain_object(
            prefs.default_subject_classification_vocabulary
        )

    @staticmethod
    def get_publication_type_vocabulary() -> VocabularyProtocol:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return vocabulary_repository.as_domain_object(prefs.default_publication_type_vocabulary)

    @staticmethod
    def get_home_currency() -> Currency:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return Currency.from_code(prefs.home_currency)

    @staticmethod
    def set_subject_classification_vocabulary(vocabulary: VocabularyProtocol) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.default_subject_classification_vocabulary_id = vocabulary.id
        prefs.save()

    @staticmethod
    def set_publication_type_vocabulary(vocabulary: VocabularyProtocol) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.default_publication_type_vocabulary_id = vocabulary.id
        prefs.save()

    @staticmethod
    def set_home_currency(currency: Currency) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.home_currency = currency.code
        prefs.save()
