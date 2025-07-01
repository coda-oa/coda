from django.db import models

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.domain.author import AuthorNames
from coda.domain.publication import License, OpenAccessType, UnpublishedState

from ._attachedentities import PublicationAttachedConcept


class Publication(models.Model):
    STATES = (("Published", "Published"), *((s.name, s.value) for s in UnpublishedState))
    OA_TYPES = tuple((t.name, t.value) for t in OpenAccessType)
    LICENSE_CHOICES = tuple((_l.name, _l.value) for _l in License)

    title = models.TextField()

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
