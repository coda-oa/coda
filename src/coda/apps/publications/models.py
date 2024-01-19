from django.db import models

from coda.apps.journals.models import Journal


class Publication(models.Model):
    title = models.CharField(max_length=255)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name="publications")


class LinkType(models.Model):
    """
    A link type specifies the kind of a link on a publication.
    Some common types are DOI and URL
    """

    name = models.CharField(max_length=255)


class Link(models.Model):
    """
    Represents a link to a resource relevant to a publication.
    """

    type = models.ForeignKey(LinkType, on_delete=models.CASCADE)
    value = models.TextField()
    publications = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="links")
