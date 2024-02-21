from typing import TypedDict

from django.db import models

from coda import orcid
from coda.apps.institutions.models import Institution
from coda.validation import as_validator

orcid_validator = as_validator(orcid.parse)


class AuthorDto(TypedDict):
    name: str
    email: str
    orcid: str | None
    affiliation: int | None


class Person(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(null=True)
    orcid = models.CharField(max_length=255, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        super().clean()
        if self.orcid:
            self.orcid = orcid_validator(self.orcid)


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
    def create_from_dto(cls, dto: AuthorDto) -> "Author":
        p = Person.objects.filter(name=dto["name"], email=dto["email"], orcid=dto["orcid"]).first()
        if p is None:
            p = Person.objects.create(name=dto["name"], email=dto["email"], orcid=dto["orcid"])
            p.full_clean()

        affiliation_pk = dto.get("affiliation")
        if affiliation_pk:
            affiliation = Institution.objects.get(pk=affiliation_pk)
        else:
            affiliation = None

        return cls.objects.create(details=p, affiliation=affiliation)
