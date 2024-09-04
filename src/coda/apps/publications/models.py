from django.db import models

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.author import AuthorList
from coda.publication import License, OpenAccessType, UnknownConcept, UnpublishedState


class Vocabulary(models.Model):
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=10, blank=True, default="")

    @staticmethod
    def empty() -> "Vocabulary":
        v, created = Vocabulary.objects.get_or_create(
            name="empty vocabulary", pk=UnknownConcept.vocabulary
        )
        if created or v.concepts.count() == 0:
            Concept.objects.create(concept_id=UnknownConcept.id, name="unknown", vocabulary=v)
        return v

    def __str__(self) -> str:
        return self.name


class Concept(models.Model):
    concept_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    hint = models.TextField()
    vocabulary = models.ForeignKey(Vocabulary, on_delete=models.CASCADE, related_name="concepts")

    def __str__(self) -> str:
        return self.name


class Publication(models.Model):
    STATES = (("Published", "Published"), *((s.name, s.value) for s in UnpublishedState))
    OA_TYPES = tuple((t.name, t.value) for t in OpenAccessType)
    LICENSE_CHOICES = tuple((_l.name, _l.value) for _l in License)

    title = models.CharField(max_length=255)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name="publications")
    submitting_author = models.OneToOneField(
        Author, on_delete=models.CASCADE, related_name="submitted_publication", null=True
    )

    subject_area = models.ForeignKey(
        Concept, on_delete=models.SET_NULL, related_name="publications_of_subject", null=True
    )
    publication_type = models.ForeignKey(
        Concept, on_delete=models.SET_NULL, related_name="publications_with_type", null=True
    )
    open_access_type = models.CharField(choices=OA_TYPES, default=OpenAccessType.Closed.name)
    license = models.CharField(choices=LICENSE_CHOICES, default=License.Unknown.name)

    publication_state = models.CharField(
        max_length=255, choices=STATES, default=UnpublishedState.Unknown.name
    )
    online_publication_date = models.DateField(null=True)
    print_publication_date = models.DateField(null=True)
    author_list = models.CharField(max_length=255, null=True, blank=True)

    @property
    def authors(self) -> AuthorList:
        return AuthorList.from_str(self.author_list or "")


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
