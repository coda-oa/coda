from coda.apps.dto import CodaBaseDto, OptionalFromStr
from coda.domain.author import Author, AuthorId, InstitutionId, Role
from coda.domain.orcid import Orcid
from coda.domain.string import NonEmptyStr


class AuthorDto(CodaBaseDto):
    name: str
    email: str
    orcid: str | None
    affiliation: OptionalFromStr[InstitutionId] = None
    role: str

    @classmethod
    def from_author(cls, author: Author) -> "AuthorDto":
        return cls(
            name=author.name,
            email=author.email,
            orcid=author.orcid,
            affiliation=author.affiliation,
            role=author.role.name,
        )

    def to_author(self, id: AuthorId | None = None) -> Author:
        return Author.restore(
            id=id,
            name=NonEmptyStr(self.name),
            email=self.email,
            orcid=Orcid(self.orcid) if self.orcid else None,
            affiliation=self.affiliation,
            role=Role[self.role],
        )
