from django.db import models

from coda.apps.institutions.models import Institution


class PersonId(models.Model):
    orcid = models.CharField(max_length=255, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Author(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(null=True)
    affiliation = models.ForeignKey(
        Institution,
        on_delete=models.SET_NULL,
        related_name="affiliated_authors",
        null=True,
        blank=True,
    )
    identifier = models.ForeignKey(
        PersonId,
        on_delete=models.CASCADE,
        related_name="authored_publications",
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
