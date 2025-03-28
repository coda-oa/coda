from typing import Annotated

import pydantic

from coda import orcid
from coda.apps.institutions import repository as institution_repository
from coda.author import Author, InstitutionId, Role
from coda.string import NonEmptyStr

Orcid = Annotated[str, pydantic.PlainValidator(orcid.Orcid)]


class AuthorImportDto(pydantic.BaseModel):
    name: str
    email: str
    orcid: Orcid | None = None
    affiliation: str | None = None
    role: Role = Role.CO_AUTHOR

    def parse(self) -> Author:
        affiliation = self._parse_affiliation()

        return Author.new(
            name=NonEmptyStr(self.name),
            email=self.email,
            orcid=orcid.Orcid(self.orcid) if self.orcid else None,
            role=self.role,
            affiliation=affiliation,
        )

    def _parse_affiliation(self) -> InstitutionId | None:
        if self.affiliation is None:
            return None

        institution = institution_repository.first_by_name(self.affiliation)
        if not institution:
            institution = institution_repository.create(self.affiliation)

        return InstitutionId(institution.id)
