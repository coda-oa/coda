from typing import TypedDict

from coda.author import Author, AuthorId, InstitutionId, Role
from coda.orcid import Orcid
from coda.string import NonEmptyStr


class AuthorDto(TypedDict):
    name: str
    email: str
    orcid: str | None
    affiliation: int | None
    roles: list[str] | None


def to_author_dto(author: Author) -> AuthorDto:
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
