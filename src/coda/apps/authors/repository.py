from typing import TypeGuard
from collections.abc import Iterable
from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author, PersonId, Role, serialize_roles
from coda.apps.institutions.models import Institution


def create(dto: AuthorDto, affiliation: Institution | None) -> Author:
    _id, _ = PersonId.objects.get_or_create(orcid=dto["orcid"])
    parsed_roles = _parse_roles(dto)
    roles = serialize_roles(parsed_roles)
    return Author.objects.create(
        name=dto["name"], email=dto["email"], identifier=_id, affiliation=affiliation, roles=roles
    )


def _parse_roles(dto: AuthorDto) -> Iterable[Role]:
    return filter(_not_none, map(_parse_role, dto["roles"] or []))


def _parse_role(r: str) -> Role | None:
    try:
        return Role[r]
    except KeyError:
        return None


def _not_none(x: Role | None) -> TypeGuard[Role]:
    return x is not None
