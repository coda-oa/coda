import enum
from django.db import models
from coda.apps.authors.models import Author

from coda.apps.journals.models import Journal


class OpenAccessType(enum.Enum):
    GOLD = "Gold"
    DIAMOND = "Diamond"
    HYBRID = "Hybrid"
    CLOSED = "Closed"


class Publication(models.Model):
    class State:
        PUBLISHED = "published"
        ACCEPTED = "accepted"
        SUBMITTED = "submitted"
        REJECTED = "rejected"

    STATES = (
        (State.PUBLISHED, "Published"),
        (State.ACCEPTED, "Accepted"),
        (State.SUBMITTED, "Submitted"),
        (State.REJECTED, "Rejected"),
    )

    OA_TYPES = tuple((t.name, t.value) for t in OpenAccessType)

    title = models.CharField(max_length=255)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name="publications")
    submitting_author = models.OneToOneField(
        Author, on_delete=models.CASCADE, related_name="submitted_publication", null=True
    )

    open_access_type = models.CharField(choices=OA_TYPES, default=OpenAccessType.CLOSED.name)

    publication_state = models.CharField(max_length=255, choices=STATES, default="submitted")
    publication_date = models.DateField(null=True)


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
