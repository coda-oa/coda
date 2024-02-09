from django.db import models

from coda import orcid
from coda.apps.institutions.models import Institution
from coda.validation import as_validator

orcid_validator = as_validator(orcid.parse)


class Person(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(null=True)
    orcid = models.CharField(max_length=255, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        super().clean()
        self.orcid = orcid_validator(self.orcid) if self.orcid else None


class Author(models.Model):
    affiliation = models.ForeignKey(
        Institution,
        on_delete=models.SET_NULL,
        related_name="affiliated_authors",
        null=True,
        blank=True,
    )
    details = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="authored_publications",
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create(
        cls, name: str, email: str, orcid: str, affiliation_pk: int | None = None
    ) -> "Author":
        p = Person.objects.filter(name=name, email=email, orcid=orcid).first()
        if p is None:
            p = Person.objects.create(name=name, email=email, orcid=orcid)
            p.full_clean()

        affiliation = Institution.objects.get(pk=affiliation_pk) if affiliation_pk else None
        return cls.objects.create(details=p, affiliation=affiliation)
