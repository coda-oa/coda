import uuid

from django.db import models

from coda.apps.contracts.models import Contract
from coda.vocabulary import UnknownConcept

from ._vocabulary import Vocabulary


class PublicationAttachedConcept(models.Model):
    entity_id = models.UUIDField(default=uuid.uuid4, unique=False)
    vocabulary = models.ForeignKey(Vocabulary, on_delete=models.CASCADE, default=Vocabulary.empty)
    name = models.CharField(max_length=255, blank=True)

    @classmethod
    def unknown(cls) -> "PublicationAttachedConcept":
        return cls.objects.create(
            entity_id=UnknownConcept.id, vocabulary_id=UnknownConcept.vocabulary
        )


class AttachedContract(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    contract_year = models.IntegerField()
    publication = models.ForeignKey(
        "Publication", on_delete=models.CASCADE, related_name="attached_contracts"
    )
