from enum import Enum
from collections.abc import Iterable
from django.db import models

from coda.apps.institutions.models import Institution


class PersonId(models.Model):
    orcid = models.CharField(max_length=255, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Role(Enum):
    SUBMITTER = "Submitter"
    CO_AUTHOR = "Co-author"
    CORRESPONDING_AUTHOR = "Corresponding author"


ROLE_SERIALIZE_SEPARATOR = "||"


def serialize_roles(roles: Iterable[Role]) -> str:
    return ROLE_SERIALIZE_SEPARATOR.join(role.name for role in roles)


def deserialize_roles(serialized: str) -> Iterable[Role]:
    return (Role[role] for role in serialized.split(ROLE_SERIALIZE_SEPARATOR))


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
    roles = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_roles(self) -> set[Role]:
        if self.roles:
            return set(deserialize_roles(self.roles))
        return set()

    def set_roles(self, roles: Iterable[Role]) -> None:
        self.roles = serialize_roles(roles)
        self.save()
