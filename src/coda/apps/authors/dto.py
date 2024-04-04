from typing import TypedDict

from coda.apps.authors.models import Author


class AuthorDto(TypedDict):
    name: str
    email: str
    orcid: str | None
    affiliation: int | None
    roles: list[str] | None


def author_dto_from_model(author: Author) -> AuthorDto:
    return AuthorDto(
        name=author.name,
        email=author.email or "",
        orcid=author.identifier.orcid if author.identifier else None,
        affiliation=author.affiliation.pk if author.affiliation else None,
        roles=[role.name for role in author.get_roles()],
    )
