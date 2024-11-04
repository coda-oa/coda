from coda.apps.dto import CodaBaseDto
from coda.author import Author, AuthorId, InstitutionId, Role
from coda.orcid import Orcid
from coda.string import NonEmptyStr


class AuthorDto(CodaBaseDto):
    name: str
    email: str
    orcid: str | None
    affiliation: InstitutionId | None
    roles: list[str] | None

    @classmethod
    def from_author(cls, author: Author) -> "AuthorDto":
        return cls(
            name=author.name,
            email=author.email,
            orcid=author.orcid,
            affiliation=author.affiliation,
            roles=[role.name for role in author.roles],
        )

    def to_author(self, id: AuthorId | None = None) -> Author:
        return Author(
            id=id,
            name=NonEmptyStr(self.name),
            email=self.email,
            orcid=Orcid(self.orcid) if self.orcid else None,
            affiliation=self.affiliation,
            roles=frozenset(Role[r] for r in self.roles or []),
        )
