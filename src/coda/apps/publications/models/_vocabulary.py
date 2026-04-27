import uuid
from django.db import models

from coda.domain.vocabulary import UnknownConcept
from coda.apps.publications.models.queryset_vocabulary import VocabularyManager


class Vocabulary(models.Model):
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=10, blank=True, default="")

    is_limited = models.BooleanField(default=False)
    base_vocabulary = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)

    objects: VocabularyManager = VocabularyManager()

    @staticmethod
    def empty() -> "Vocabulary":
        v, created = Vocabulary.objects.get_or_create(
            name="empty vocabulary", pk=UnknownConcept.vocabulary
        )
        if created or v.concepts.count() == 0:
            Concept.objects.create(
                concept_id=UnknownConcept.concept_id, name="unknown", vocabulary=v
            )
        return v

    @staticmethod
    def ensure_empty() -> None:
        """Ensure that the empty vocabulary exists."""
        Vocabulary.empty()

    def __str__(self) -> str:
        return self.name


class Concept(models.Model):
    entity_id = models.UUIDField(default=uuid.uuid4)
    concept_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    hint = models.TextField()
    vocabulary = models.ForeignKey(Vocabulary, on_delete=models.CASCADE, related_name="concepts")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )

    @classmethod
    def unknown(cls) -> "Concept":
        c, _ = Concept.objects.get_or_create(
            concept_id=UnknownConcept.concept_id,
            vocabulary_id=UnknownConcept.vocabulary,
            name="unknown",
        )

        return c

    def __str__(self) -> str:
        return self.name
