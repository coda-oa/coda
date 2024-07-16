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
