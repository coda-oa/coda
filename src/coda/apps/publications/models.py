import uuid

from django.db import models

from coda.apps.contracts.models import Contract
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.author import AuthorNames
from coda.publication import License, OpenAccessType, UnpublishedState
from coda.vocabulary import UnknownConcept


class Vocabulary(models.Model):
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=10, blank=True, default="")

    is_limited = models.BooleanField(default=False)
    base_vocabulary = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)

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

    def __str__(self) -> str:
        return self.name


class Concept(models.Model):
    entity_id = models.UUIDField(default=uuid.uuid4)
    concept_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    hint = models.TextField()
    vocabulary = models.ForeignKey(Vocabulary, on_delete=models.CASCADE, related_name="concepts")

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


class Publication(models.Model):
    STATES = (("Published", "Published"), *((s.name, s.value) for s in UnpublishedState))
    OA_TYPES = tuple((t.name, t.value) for t in OpenAccessType)
    LICENSE_CHOICES = tuple((_l.name, _l.value) for _l in License)

    title = models.CharField(max_length=255)

    article_journal = models.ForeignKey(
        Journal, on_delete=models.CASCADE, related_name="publications", null=True
    )
    monograph_publisher = models.ForeignKey(
        Publisher, on_delete=models.CASCADE, related_name="publications", null=True
    )

    subject_area = models.OneToOneField(
        PublicationAttachedConcept,
        on_delete=models.CASCADE,
        related_name="+",
        default=PublicationAttachedConcept.unknown,
    )

    publication_type = models.OneToOneField(
        PublicationAttachedConcept,
        on_delete=models.CASCADE,
        related_name="+",
        default=PublicationAttachedConcept.unknown,
    )

    open_access_type = models.CharField(choices=OA_TYPES, default=OpenAccessType.Closed.name)
    license = models.CharField(choices=LICENSE_CHOICES, default=License.Unknown.name)

    publication_state = models.CharField(
        max_length=255, choices=STATES, default=UnpublishedState.Unknown.name
    )

    online_publication_date = models.DateField(null=True)
    print_publication_date = models.DateField(null=True)
    author_list = models.TextField(null=True, blank=True)

    @property
    def authors(self) -> AuthorNames:
        return AuthorNames.from_str(self.author_list or "")


class LinkType(models.Model):
    """
    A link type specifies the kind of a link on a publication.
    Some common types are DOI and URL
    """

    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name


class Link(models.Model):
    """
    Represents a link to a resource relevant to a publication.
    """

    type = models.ForeignKey(LinkType, on_delete=models.CASCADE)
    value = models.TextField()
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="links")
