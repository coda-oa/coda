from typing import TypedDict


class AuthorDto(TypedDict):
    name: str
    email: str
    orcid: str | None
    affiliation: int | None
    roles: list[str] | None
