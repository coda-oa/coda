from collections.abc import Iterable
from typing import TypeGuard, cast

from django.core.exceptions import ValidationError

from coda import orcid
from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author, PersonId, Role, serialize_roles
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.validation import as_validator

orcid_validator = as_validator(orcid.parse)


def author_create(dto: AuthorDto) -> Author:
    _validate(dto)
    affiliation = _find_affiliation(dto)
    _id, _ = PersonId.objects.get_or_create(orcid=dto["orcid"])
    parsed_roles = _parse_roles(dto)
    roles = serialize_roles(parsed_roles)
    return Author.objects.create(
        name=dto["name"], email=dto["email"], identifier=_id, affiliation=affiliation, roles=roles
    )


def author_update(author: Author, dto: AuthorDto) -> Author:
    _validate(dto)
    identifier = cast(PersonId, author.identifier)
    identifier.orcid = dto["orcid"]
    identifier.save()

    author.name = dto["name"]
    author.email = dto["email"]
    if dto["affiliation"]:
        author.affiliation = _find_affiliation(dto)

    if dto["roles"]:
        author.set_roles(_parse_roles(dto))

    author.save()
    return author


def _validate(dto: AuthorDto) -> None:
    if not dto["name"]:
        raise ValidationError("Author name is required")

    if dto["orcid"]:
        orcid_validator(dto["orcid"])


def _find_affiliation(dto: AuthorDto) -> Institution | None:
    affiliation_pk = dto.get("affiliation")
    if affiliation_pk:
        affiliation = institution_repository.get_by_id(affiliation_pk)
    else:
        affiliation = None
    return affiliation


def _parse_roles(dto: AuthorDto) -> Iterable[Role]:
    def _not_none(x: Role | None) -> TypeGuard[Role]:
        return x is not None

    return filter(_not_none, map(_parse_role, dto["roles"] or []))


def _parse_role(r: str) -> Role | None:
    if not r:
        return None
    try:
        return Role[r]
    except KeyError:
        raise ValidationError(f"Invalid role: {r}")
