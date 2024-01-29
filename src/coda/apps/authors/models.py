from django.db import models

from coda.apps.institutions.models import Institution


class Author(models.Model):
    affiliation = models.ForeignKey(
        Institution,
        on_delete=models.SET_NULL,
        related_name="affiliated_authors",
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Person(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    orcid = models.CharField(max_length=255)
    author_entries = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="details")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
