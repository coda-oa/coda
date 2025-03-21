from typing import Annotated
from coda import orcid
from coda.author import Author, Role
from coda.string import NonEmptyStr


import pydantic

Orcid = Annotated[str, pydantic.PlainValidator(orcid.Orcid)]


class AuthorImportDto(pydantic.BaseModel):
    name: str
    email: str
    orcid: Orcid | None
    role: Role

    def parse(self) -> Author:
        return Author.new(
            name=NonEmptyStr(self.name),
            email=self.email,
            orcid=orcid.Orcid(self.orcid) if self.orcid else None,
            role=self.role,
        )
