from django.db import models


class Author(models.Model):
    affiliation = models.CharField(max_length=255)


class Person(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    orcid = models.CharField(max_length=255)
    author_entries = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="details")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
