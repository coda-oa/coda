from typing import TypedDict

from coda.apps.authors.models import Author as AuthorModel
from coda.author import Author, AuthorId, InstitutionId, Role
from coda.orcid import Orcid
from coda.string import NonEmptyStr


class AuthorDto(TypedDict):
    name: str
    email: str
    orcid: str | None
    affiliation: int | None
    roles: list[str] | None


def author_dto_from_model(author: AuthorModel) -> AuthorDto:
    return AuthorDto(
        name=author.name,
        email=author.email or "",
        orcid=author.identifier.orcid if author.identifier else None,
        affiliation=author.affiliation.pk if author.affiliation else None,
        roles=[role.name for role in author.get_roles()],
    )


def as_dto(author: Author) -> AuthorDto:
    return AuthorDto(
        name=author.name,
        email=author.email,
        orcid=author.orcid,
        affiliation=author.affiliation,
        roles=[role.name for role in author.roles],
    )


def parse_author(author_dto: AuthorDto, id: AuthorId | None = None) -> Author:
    return Author(
        id=id,
        name=NonEmptyStr(author_dto["name"]),
        email=author_dto["email"],
        orcid=Orcid(author_dto["orcid"]) if author_dto["orcid"] else None,
        affiliation=InstitutionId(author_dto["affiliation"]) if author_dto["affiliation"] else None,
        roles=frozenset(Role[r] for r in author_dto["roles"] or []),
    )
