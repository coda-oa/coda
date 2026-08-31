from typing import cast

from django.db.models import QuerySet

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import PersonId
from coda.apps.mappers import prefixed
from coda.domain.author import Author, AuthorId, InstitutionId, Role
from coda.domain.orcid import Orcid
from coda.domain.string import NonEmptyStr


class AuthorDomainMapper:
    @staticmethod
    def prefetch(qs: QuerySet[AuthorModel], prefix: str = "") -> QuerySet[AuthorModel]:
        return qs.select_related(
            prefixed(prefix, "identifier"), prefixed(prefix, "affiliation")
        ).order_by("id")

    @staticmethod
    def map(model: AuthorModel) -> Author:
        person_id = cast(PersonId, model.identifier)
        return Author.restore(
            id=AuthorId(model.pk),
            name=NonEmptyStr(model.name),
            email=model.email or "",
            orcid=Orcid(person_id.orcid) if person_id.orcid else None,
            affiliation=InstitutionId(model.affiliation.pk) if model.affiliation else None,
            role=AuthorDomainMapper.deserialize_role(model.roles or ""),
        )

    @staticmethod
    def deserialize_role(serialized: str) -> Role:
        return Role[serialized]
