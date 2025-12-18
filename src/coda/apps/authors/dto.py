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
        """
        Convert DTO to Author domain object.

        Uses Author.new() to ensure validation of business rules when converting
        user-submitted form data. The id parameter is primarily for testing purposes,
        as new authors from forms typically don't have IDs yet.
        """
        author = Author.new(
            name=NonEmptyStr(self.name),
            email=self.email,
            orcid=Orcid(self.orcid) if self.orcid else None,
            affiliation=self.affiliation,
            role=Role[self.role],
        )
        # Set ID if provided (used in testing scenarios)
        if id is not None:
            author.id = id
        return author
