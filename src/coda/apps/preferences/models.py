from django.db import models

from coda.apps.publications.models import Vocabulary
from coda.money import Currency


def empty_vocabulary() -> Vocabulary:
    v, _ = Vocabulary.objects.get_or_create(name="empty vocabulary")
    return v


class GlobalPreferences(models.Model):
    home_currency = models.CharField(max_length=255, default=Currency.EUR.code)
    default_subject_classification_vocabulary = models.ForeignKey(
        Vocabulary,
        on_delete=models.SET_DEFAULT,
        default=empty_vocabulary,
        related_name="+",
    )
    default_publication_type_vocabulary = models.ForeignKey(
        Vocabulary,
        on_delete=models.SET_DEFAULT,
        default=empty_vocabulary,
        related_name="+",
    )

    @staticmethod
    def get_subject_classification_vocabulary() -> Vocabulary:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return prefs.default_subject_classification_vocabulary

    @staticmethod
    def get_publication_type_vocabulary() -> Vocabulary:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return prefs.default_publication_type_vocabulary

    @staticmethod
    def get_home_currency() -> Currency:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        return Currency.from_code(prefs.home_currency)

    @staticmethod
    def set_subject_classification_vocabulary(vocabulary: Vocabulary) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.default_subject_classification_vocabulary = vocabulary
        prefs.save()

    @staticmethod
    def set_publication_type_vocabulary(vocabulary: Vocabulary) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.default_publication_type_vocabulary = vocabulary
        prefs.save()

    @staticmethod
    def set_home_currency(currency: Currency) -> None:
        prefs, _ = GlobalPreferences.objects.get_or_create()
        prefs.home_currency = currency.code
        prefs.save()
