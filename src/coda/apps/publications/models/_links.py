from django.db import models

from ._publication import Publication


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
