import enum
from django.db import models
from coda.apps.authors.models import Author

from coda.apps.journals.models import Journal
from coda.authorlist import AuthorList


class OpenAccessType(enum.Enum):
    GOLD = "Gold"
    DIAMOND = "Diamond"
    HYBRID = "Hybrid"
    CLOSED = "Closed"


class License(enum.Enum):
    CC_BY = "CC-BY"
    CC_BY_SA = "CC-BY-SA"
    CC_BY_NC = "CC-BY-NC"
    CC_BY_NC_SA = "CC-BY-NC-SA"
    CC_BY_NC_ND = "CC-BY-NC-ND"
    CC_BY_ND = "CC-BY-ND"
    CC0 = "CC0"
    PROPRIETARY = "Proprietary"
    NONE = "None"
    UNKNOWN = "Unknown"


class Publication(models.Model):
    class State:
        PUBLISHED = "published"
        ACCEPTED = "accepted"
        SUBMITTED = "submitted"
        REJECTED = "rejected"
        UNKNOWN = "unknown"

    STATES = (
        (State.PUBLISHED, "Published"),
        (State.ACCEPTED, "Accepted"),
        (State.SUBMITTED, "Submitted"),
        (State.REJECTED, "Rejected"),
        (State.UNKNOWN, "Unknown"),
    )

    OA_TYPES = tuple((t.name, t.value) for t in OpenAccessType)

    LICENSE_CHOICES = tuple((_l.name, _l.value) for _l in License)

    title = models.CharField(max_length=255)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name="publications")
    submitting_author = models.OneToOneField(
        Author, on_delete=models.CASCADE, related_name="submitted_publication", null=True
    )

    open_access_type = models.CharField(choices=OA_TYPES, default=OpenAccessType.CLOSED.name)
    license = models.CharField(choices=LICENSE_CHOICES, default=License.UNKNOWN.name)

    publication_state = models.CharField(max_length=255, choices=STATES, default=State.UNKNOWN)
    publication_date = models.DateField(null=True)
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
